// OpenGSD Path desktop app: a tray icon and a window around the gsd-path
// daemon. Every rule lives in the Python daemon (`gsd_daemon launch`); this
// shell finds Python, acts on the launch result, stops only the daemon process
// it started, and carries the frontend's requests to the daemon.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{self, OpenOptions};
use std::process::{Child, Command, Stdio};
use std::path::PathBuf;
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Serialize;
use serde_json::Value;
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::path::BaseDirectory;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent, Wry};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_positioner::{Position, WindowExt};

// Daemon DEFAULT_PORT (daemon/gsd_daemon/serve.py).
const DEFAULT_PORT: u16 = 8765;
// Poll and request budgets of the Swift tray app this replaces (AppDelegate.swift, StatusClient.swift).
const POLL: Duration = Duration::from_secs(5);
const STATUS_TIMEOUT: Duration = Duration::from_secs(3);
const TRAY_ID: &str = "main";
// The tray popover window (src/screens/Tray.tsx).
const POPOVER: &str = "tray";
// One click on the tray icon can first take focus from the popover (which hides it) and then
// arrive as a click. The longest press that is still one click: the Windows default double-click time.
const CLICK: Duration = Duration::from_millis(500);
// The argument the login entry passes: start in the tray, with no window.
const HIDDEN_ARG: &str = "--hidden";

/// What the frontend shows (src/shell.ts). `launch` is the daemon's launch JSON, passed through.
#[derive(Clone, Serialize)]
struct ShellState {
    phase: &'static str, // checking | blocked | ready
    os: &'static str,
    port: u16,
    python_missing: bool,
    launch: Option<Value>,
    error: Option<String>,
    autostart: bool,
    owned: bool, // this app started the daemon, so it can stop and restart it
    version: String,
    update: Option<UpdateInfo>,    // a newer app version that is ready to install
    update_error: Option<String>, // the last check or install failed; with `update` set, the update was refused
}

#[derive(Clone, Serialize, PartialEq, Debug)]
struct UpdateInfo {
    version: String,
    notes: Option<String>,
}

struct Shell {
    python: Option<Vec<String>>,
    path: Option<String>, // the PATH child processes get; None: this process's own
    child: Option<Child>,
    view: ShellState,
    popover_hidden: Option<Instant>, // when a focus loss hid the tray popover
}

/// The shell, and the lock one launch check holds from start to end.
struct AppState(Mutex<Shell>, Mutex<()>);

/// What to do with a launch result. Anything that is not a clean start or reuse blocks.
#[derive(Debug, PartialEq)]
enum Next {
    Start(Vec<String>),
    Reuse,
    Blocked,
}

fn decide(launch: &Value) -> Next {
    let blocking = launch["problems"]
        .as_array()
        .map_or(false, |problems| problems.iter().any(|problem| problem["blocking"] != Value::Bool(false)));
    if blocking {
        return Next::Blocked;
    }
    match launch["action"].as_str() {
        Some("reuse") => Next::Reuse,
        Some("start") => match serde_json::from_value::<Vec<String>>(launch["serve_argv"].clone()) {
            Ok(argv) if !argv.is_empty() => Next::Start(argv),
            _ => Next::Blocked,
        },
        _ => Next::Blocked,
    }
}

/// Launch at login is turned on one time, so a user who turns it off keeps it off.
fn enables_autostart(ready: bool, autostart_ok: bool, already_set: bool) -> bool {
    ready && autostart_ok && !already_set
}

/// The tray click that follows a focus-loss hide is the click that closed the popover.
fn closed_by_this_click(hidden: Option<Instant>, now: Instant) -> bool {
    hidden.map_or(false, |at| now.duration_since(at) < CLICK)
}

/// A start at login stays in the tray, unless the user must act.
fn opens_window_after_boot(hidden: bool, phase: &str) -> bool {
    hidden && phase == "blocked"
}

/// The PATH a child process printed between two `__PATH__` marks.
fn marked_path(output: &str) -> Option<String> {
    output.split("__PATH__").nth(1).filter(|path| !path.is_empty()).map(str::to_string)
}

#[derive(Clone, PartialEq)]
struct TrayView {
    text: String,
    running: bool,
    owned: bool,
    attention: bool,
    update: Option<String>,
    setup: bool,
}

fn port(app: &AppHandle) -> u16 {
    app.state::<AppState>().0.lock().unwrap().view.port
}

fn app_dir(app: &AppHandle) -> Option<PathBuf> {
    Some(app.path().home_dir().ok()?.join(".gsd-path").join("app"))
}

/// GSD_PATH_APP_PORT (side-by-side testing), then the port the user chose, then the default.
fn initial_port(app: &AppHandle) -> u16 {
    let saved = || fs::read_to_string(app_dir(app)?.join("port")).ok();
    std::env::var("GSD_PATH_APP_PORT")
        .ok()
        .or_else(saved)
        .and_then(|text| text.trim().parse().ok())
        .unwrap_or(DEFAULT_PORT)
}

fn os_name() -> &'static str {
    if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(windows) {
        "windows"
    } else {
        "linux"
    }
}

/// The daemon address for a frontend request. The host is fixed; only the path varies.
fn api_url(port: u16, method: &str, path: &str) -> Result<String, String> {
    if method != "GET" && method != "POST" {
        return Err(format!("unsupported method {method}"));
    }
    if !path.starts_with('/') {
        return Err("the path must start with /".into());
    }
    Ok(format!("http://127.0.0.1:{port}{path}"))
}

// -- processes --------------------------------------------------------------------

/// A child process. `path` is its PATH, which also finds the program.
fn command(argv: &[String], path: Option<&str>) -> Command {
    let mut command = Command::new(&argv[0]);
    command.args(&argv[1..]).stdin(Stdio::null());
    if let Some(path) = path {
        command.env("PATH", path);
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    command
}

/// The PATH a new terminal would get, so a program installed after the app started is found.
/// Unix: apps started from Finder or a desktop menu get a minimal PATH; read the login shell's.
/// Windows: a running process keeps its first PATH; read the machine and user values again
/// (.NET expands their %VAR% references).
fn fresh_path() -> Option<String> {
    let argv: Vec<String> = if cfg!(windows) {
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output ('__PATH__'+\
          [Environment]::GetEnvironmentVariable('Path','Machine')+';'+\
          [Environment]::GetEnvironmentVariable('Path','User')+'__PATH__')"]
            .map(String::from).into()
    } else {
        vec![std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".into()), "-l".into(), "-c".into(),
             "printf '\\n__PATH__%s__PATH__' \"$PATH\"".into()]
    };
    let output = command(&argv, None).output().ok()?;
    marked_path(&String::from_utf8_lossy(&output.stdout))
}

fn child_path(app: &AppHandle) -> Option<String> {
    app.state::<AppState>().0.lock().unwrap().path.clone()
}

fn find_python(path: Option<&str>) -> Option<Vec<String>> {
    let candidates: &[&[&str]] = if cfg!(windows) {
        &[&["py", "-3"], &["python"], &["python3"]]
    } else {
        &[&["python3"], &["python"]]
    };
    candidates
        .iter()
        .map(|argv| argv.iter().map(|part| part.to_string()).collect::<Vec<_>>())
        .find(|argv| {
            command(argv, path)
                .args(["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .map(|status| status.success())
                .unwrap_or(false)
        })
}

fn run_launch(app: &AppHandle, python: &[String]) -> Result<Value, String> {
    let bundle = app.path().resolve("daemon", BaseDirectory::Resource).map_err(|e| e.to_string())?;
    let output = command(python, child_path(app).as_deref())
        .args(["-B", "-m", "gsd_daemon", "launch", "--port", &port(app).to_string()])
        .env("PYTHONPATH", &bundle)
        .current_dir(&bundle)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(stderr.trim().lines().last().unwrap_or("no error output").to_string());
    }
    serde_json::from_slice(&output.stdout).map_err(|e| e.to_string())
}

fn start_daemon(app: &AppHandle, argv: &[String]) -> Result<Child, String> {
    let logs = app.path().home_dir().map_err(|e| e.to_string())?.join(".gsd-path").join("logs");
    fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let log = OpenOptions::new().create(true).append(true).open(logs.join("app-daemon.log")).map_err(|e| e.to_string())?;
    let err = log.try_clone().map_err(|e| e.to_string())?;
    let mut child = command(argv, child_path(app).as_deref()).stdout(log).stderr(err).spawn().map_err(|e| e.to_string())?;
    // The daemon binds its port before its first scan; wait for it or for its exit.
    loop {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("the daemon exited during startup ({status})"));
        }
        if fetch_status(port(app)).is_some() {
            return Ok(child);
        }
        thread::sleep(Duration::from_millis(100));
    }
}

/// Stop the daemon this app started. True when there was one.
fn stop_owned(app: &AppHandle) -> bool {
    let child = app.state::<AppState>().0.lock().unwrap().child.take();
    let Some(mut child) = child else { return false };
    let _ = child.kill();
    let _ = child.wait();
    true
}

fn publish(app: &AppHandle, change: impl FnOnce(&mut ShellState)) -> ShellState {
    let view = {
        let state = app.state::<AppState>();
        let mut shell = state.0.lock().unwrap();
        change(&mut shell.view);
        shell.view.owned = shell.child.is_some();
        shell.view.clone()
    };
    let _ = app.emit("shell", &view);
    refresh_tray(app);
    view
}

/// Run the launch check and act on it. Runs off the main thread. A request that arrives
/// while a check runs waits for that check and returns its result.
fn boot(app: &AppHandle) -> ShellState {
    let state = app.state::<AppState>();
    let Ok(_running) = state.1.try_lock() else {
        drop(state.1.lock());
        return state.0.lock().unwrap().view.clone();
    };
    run_boot(app)
}

/// One launch check. The caller holds the boot lock.
fn run_boot(app: &AppHandle) -> ShellState {
    publish(app, |view| view.phase = "checking");
    let path = fresh_path();
    let python = {
        let state = app.state::<AppState>();
        let mut shell = state.0.lock().unwrap();
        if path.is_some() {
            shell.path = path;
        }
        if shell.python.is_none() {
            shell.python = find_python(shell.path.as_deref());
        }
        shell.python.clone()
    };
    let Some(python) = python else {
        return publish(app, |view| {
            (view.phase, view.python_missing, view.launch, view.error) = ("blocked", true, None, None);
        });
    };
    let launch = match run_launch(app, &python) {
        Ok(launch) => launch,
        Err(error) => {
            return publish(app, |view| {
                (view.phase, view.python_missing, view.launch, view.error) = ("blocked", false, None, Some(error));
            });
        }
    };
    let mut error = None;
    let mut phase = "ready";
    match decide(&launch) {
        Next::Start(argv) => {
            stop_owned(app); // a start replaces the stored process; never drop one that still runs
            match start_daemon(app, &argv) {
                Ok(child) => app.state::<AppState>().0.lock().unwrap().child = Some(child),
                Err(failure) => {
                    phase = "blocked";
                    error = Some(format!("The monitor did not start: {failure}. See ~/.gsd-path/logs/app-daemon.log."));
                }
            }
        }
        Next::Reuse => {}
        Next::Blocked => phase = "blocked",
    }
    // Launch at login waits until every old startup entry is proven gone.
    let autostart = app.autolaunch();
    if let Some(dir) = app_dir(app).filter(|_| !cfg!(debug_assertions)) {
        let marker = dir.join("autostart-set");
        if enables_autostart(phase == "ready", launch["autostart_ok"] == Value::Bool(true), marker.exists())
            && autostart.enable().is_ok()
        {
            let _ = fs::create_dir_all(&dir);
            let _ = fs::write(&marker, "");
        }
    }
    let enabled = autostart.is_enabled().unwrap_or(false);
    publish(app, move |view| {
        (view.phase, view.python_missing, view.launch, view.error, view.autostart) =
            (phase, false, Some(launch), error, enabled);
    })
}

// -- window and commands ------------------------------------------------------------

/// Script for the main window: go to one project's page (src/route.ts).
fn project_script(root: &str) -> String {
    format!("location.hash='#/project/'+encodeURIComponent({})", Value::from(root))
}

/// Show the main window. `script` runs in it after it shows.
fn show_window(app: &AppHandle, script: Option<String>) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        let window = handle.get_webview_window("main").or_else(|| {
            WebviewWindowBuilder::new(&handle, "main", WebviewUrl::App("index.html".into()))
                .title("OpenGSD Path")
                .inner_size(1200.0, 800.0)
                .build()
                .ok()
        });
        if let Some(window) = window {
            let _ = window.show();
            let _ = window.set_focus();
            if let Some(script) = &script {
                let _ = window.eval(script.as_str());
            }
        }
    });
}

/// Left click on the tray icon: show the popover next to the icon, or hide it.
/// The size has no design value for the height; the list scrolls inside it.
fn toggle_popover(app: &AppHandle) {
    let window = app.get_webview_window(POPOVER).or_else(|| {
        WebviewWindowBuilder::new(app, POPOVER, WebviewUrl::App("index.html#/tray".into()))
            .title("OpenGSD Path")
            .inner_size(380.0, 560.0)
            .resizable(false)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .visible(false)
            .build()
            .ok()
    });
    let Some(window) = window else { return };
    let hidden = app.state::<AppState>().0.lock().unwrap().popover_hidden.take();
    if closed_by_this_click(hidden, Instant::now()) {
        return;
    }
    if window.is_visible().unwrap_or(false) {
        let _ = window.hide();
        return;
    }
    let _ = window.move_window_constrained(Position::TrayCenter);
    let _ = window.show();
    let _ = window.set_focus();
}

fn spawn_boot(app: &AppHandle) {
    let app = app.clone();
    thread::spawn(move || boot(&app));
}

#[tauri::command]
fn shell_state(state: tauri::State<AppState>) -> ShellState {
    state.0.lock().unwrap().view.clone()
}

#[tauri::command]
async fn boot_command(app: AppHandle) -> Result<ShellState, String> {
    tauri::async_runtime::spawn_blocking(move || boot(&app)).await.map_err(|e| e.to_string())
}

/// Move to another port (the "port in use" screen), remember it, and run the launch check again.
#[tauri::command]
async fn use_port(app: AppHandle, port: u16) -> Result<ShellState, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<AppState>();
        let _running = state.1.lock();
        stop_owned(&app);
        if let Some(dir) = app_dir(&app) {
            let _ = fs::create_dir_all(&dir);
            let _ = fs::write(dir.join("port"), port.to_string());
        }
        state.0.lock().unwrap().view.port = port;
        run_boot(&app)
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn open_url(app: AppHandle, url: String) -> Result<(), String> {
    if !url.starts_with("https://") && !url.starts_with("http://127.0.0.1:") {
        return Err("only https and local dashboard links can be opened".into());
    }
    app.opener().open_url(url, None::<&str>).map_err(|e| e.to_string())
}

/// A button in the tray popover: an id of the native tray menu. With `root`, "open" shows that project.
/// The OS folder dialog, for watched and excluded folders. None when the user cancels.
#[tauri::command]
async fn pick_folder(app: AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    tauri::async_runtime::spawn_blocking(move || app.dialog().file().blocking_pick_folder())
        .await
        .ok()
        .flatten()
        .and_then(|folder| folder.into_path().ok())
        .map(|path| path.to_string_lossy().into_owned())
}

// -- app update -------------------------------------------------------------------

/// What a finished update check means for the shell state.
fn checked(view: &mut ShellState, result: Result<Option<UpdateInfo>, String>) {
    match result {
        Ok(found) => (view.update, view.update_error) = (found, None),
        // A failed check keeps an update that an earlier check found.
        Err(error) => view.update_error = Some(error),
    }
}

async fn find_update(app: &AppHandle) -> Result<Option<tauri_plugin_updater::Update>, String> {
    use tauri_plugin_updater::UpdaterExt;
    app.updater().map_err(|e| e.to_string())?.check().await.map_err(|e| e.to_string())
}

/// Ask the update server (latest.json on the app-latest pre-release) for a newer version.
#[tauri::command]
async fn check_update(app: AppHandle) -> ShellState {
    let result = find_update(&app)
        .await
        .map(|found| found.map(|update| UpdateInfo { version: update.version.clone(), notes: update.body.clone() }));
    publish(&app, move |view| checked(view, result))
}

/// What follows the install step. `stopped`: the owned monitor was stopped for it.
#[derive(Debug, PartialEq)]
enum AfterInstall {
    Restart,
    Refused { error: String, start_monitor: bool },
}

fn after_install(result: Result<(), String>, stopped: bool) -> AfterInstall {
    match result {
        Ok(()) => AfterInstall::Restart, // the new version starts its own monitor
        Err(error) => AfterInstall::Refused { error, start_monitor: stopped },
    }
}

fn refuse_update(app: &AppHandle, error: String) -> Result<(), String> {
    let reason = error.clone();
    publish(app, move |view| view.update_error = Some(reason));
    Err(error)
}

/// Download the update, verify its signature, stop the owned monitor, install, and restart.
/// An update whose signature does not match is refused by the updater; nothing is changed then.
#[tauri::command]
async fn install_update(app: AppHandle) -> Result<(), String> {
    let downloaded = async {
        let update = find_update(&app).await?.ok_or("no update is available")?;
        let bytes = update.download(|_, _| {}, || {}).await.map_err(|e| e.to_string())?;
        Ok::<_, String>((update, bytes))
    }
    .await;
    let (update, bytes) = match downloaded {
        Ok(ready) => ready,
        Err(error) => return refuse_update(&app, error),
    };
    // The monitor stops before the install: on Windows the installer step ends this process.
    let stopped = stop_owned(&app);
    match after_install(update.install(bytes).map_err(|e| e.to_string()), stopped) {
        AfterInstall::Restart => app.restart(),
        AfterInstall::Refused { error, start_monitor } => {
            if start_monitor {
                spawn_boot(&app);
            }
            refuse_update(&app, error)
        }
    }
}

/// Settings → App → Launch at login.
#[tauri::command]
fn set_autostart(app: AppHandle, enabled: bool) -> Result<ShellState, String> {
    let autostart = app.autolaunch();
    if enabled { autostart.enable() } else { autostart.disable() }.map_err(|e| e.to_string())?;
    let now = autostart.is_enabled().unwrap_or(false);
    Ok(publish(&app, move |view| view.autostart = now))
}

/// Settings → App → Open logs.
#[tauri::command]
fn open_logs(app: AppHandle) -> Result<(), String> {
    let logs = app.path().home_dir().map_err(|e| e.to_string())?.join(".gsd-path").join("logs");
    fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    app.opener().open_path(logs.to_string_lossy(), None::<&str>).map_err(|e| e.to_string())
}

#[tauri::command]
fn tray_action(app: AppHandle, action: String, root: Option<String>) {
    match root {
        Some(root) if action == "open" => show_window(&app, Some(project_script(&root))),
        // The main window opens the app update dialog (src/App.tsx).
        _ if action == "app-update" => {
            show_window(&app, None);
            let _ = app.emit_to("main", "show-update", ());
        }
        _ => on_menu(&app, &action),
    }
}

/// One request from the frontend to the daemon. The write token is added here, so
/// it never enters the web view.
#[tauri::command]
async fn api(app: AppHandle, method: String, path: String, body: Option<Value>) -> Result<Value, String> {
    let url = api_url(port(&app), &method, &path)?;
    let token = app_dir(&app).and_then(|dir| fs::read_to_string(dir.join("api-token")).ok());
    tauri::async_runtime::spawn_blocking(move || {
        let agent = ureq::AgentBuilder::new().build();
        let response = if method == "GET" {
            agent.get(&url).call()
        } else {
            let mut request = agent.post(&url).set("Content-Type", "application/json");
            if let Some(token) = &token {
                request = request.set("X-GSD-Path-Token", token.trim());
            }
            request.send_string(&body.unwrap_or(Value::Object(Default::default())).to_string())
        };
        match response {
            Ok(response) => {
                let text = response.into_string().map_err(|e| e.to_string())?;
                serde_json::from_str(&text).map_err(|e| e.to_string())
            }
            // The daemon explains a refusal in {"error": ...}; pass that text on.
            Err(ureq::Error::Status(code, response)) => {
                let text = response.into_string().unwrap_or_default();
                let message = serde_json::from_str::<Value>(&text)
                    .ok()
                    .and_then(|value| value["error"].as_str().map(str::to_string))
                    .unwrap_or_else(|| format!("the monitor answered {code}"));
                Err(message)
            }
            Err(error) => Err(error.to_string()),
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

// -- tray ---------------------------------------------------------------------------

fn fetch_status(port: u16) -> Option<Value> {
    let agent = ureq::AgentBuilder::new().timeout(STATUS_TIMEOUT).build();
    let body = agent.get(&format!("http://127.0.0.1:{port}/status")).call().ok()?.into_string().ok()?;
    serde_json::from_str(&body).ok()
}

fn tray_view(app: &AppHandle) -> TrayView {
    let (owned, setup, port) = {
        let state = app.state::<AppState>();
        let mut shell = state.0.lock().unwrap();
        let alive = matches!(shell.child.as_mut().map(|child| child.try_wait()), Some(Ok(None)));
        if !alive {
            shell.child = None;
        }
        (alive, shell.view.phase == "blocked", shell.view.port)
    };
    let Some(status) = fetch_status(port) else {
        return TrayView { text: "OpenGSD Path: daemon offline".into(), running: false, owned, attention: false, update: None, setup };
    };
    let projects = status["projects"].as_array().cloned().unwrap_or_default();
    // The daemon computes each project's attention list; the tray only counts it.
    let attention = projects
        .iter()
        .filter(|project| project["attention"].as_array().map_or(false, |items| !items.is_empty()))
        .count();
    let update = (status["plugin"]["update_available"].as_bool() == Some(true))
        .then(|| format!("OpenGSD Path update available — v{}", status["plugin"]["latest"].as_str().unwrap_or("?")));
    TrayView {
        text: format!("OpenGSD Path: {} projects, {} need attention", projects.len(), attention),
        running: true,
        owned,
        attention: attention > 0,
        update,
        setup,
    }
}

fn tray_menu(app: &AppHandle, view: &TrayView) -> tauri::Result<Menu<Wry>> {
    let item = |id: &str, text: &str, enabled: bool| MenuItem::with_id(app, id, text, enabled, None::<&str>);
    let menu = Menu::with_items(app, &[
        &item("status", &view.text, false)?,
        &PredefinedMenuItem::separator(app)?,
        &item("open", "Open Dashboard", true)?,
        &item("browser", "Open in Browser", view.running)?,
        &PredefinedMenuItem::separator(app)?,
        &item("start", "Start", !view.running)?,
        &item("stop", "Stop", view.owned)?,
        &item("restart", "Restart", view.owned)?,
    ])?;
    if let Some(update) = &view.update {
        menu.append(&PredefinedMenuItem::separator(app)?)?;
        menu.append(&item("update", update, true)?)?;
    }
    if view.setup {
        menu.append(&item("setup", "Setup needs attention…", true)?)?;
    }
    menu.append(&PredefinedMenuItem::separator(app)?)?;
    menu.append(&item("quit", "Quit", true)?)?;
    Ok(menu)
}

fn tray_icon(attention: bool) -> Image<'static> {
    let bytes: &'static [u8] = match (cfg!(target_os = "macos"), attention) {
        (true, false) => include_bytes!("../icons/icon-tray.png"),
        (true, true) => include_bytes!("../icons/icon-attention.png"),
        // Template glyphs are black; other desktops get the colored mark.
        (false, _) => include_bytes!("../icons/icon-brand.png"),
    };
    Image::from_bytes(bytes).expect("bundled tray icon")
}

fn apply_view(app: &AppHandle, view: &TrayView) {
    let Some(tray) = app.tray_by_id(TRAY_ID) else { return };
    if let Ok(menu) = tray_menu(app, view) {
        let _ = tray.set_menu(Some(menu));
    }
    let _ = tray.set_tooltip(Some(&view.text));
    let _ = tray.set_icon(Some(tray_icon(view.attention)));
    let _ = tray.set_icon_as_template(cfg!(target_os = "macos"));
}

fn refresh_tray(app: &AppHandle) {
    let view = tray_view(app);
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || apply_view(&handle, &view));
}

fn on_menu(app: &AppHandle, id: &str) {
    match id {
        "open" | "update" | "setup" => show_window(app, None),
        "browser" => {
            let _ = app.opener().open_url(format!("http://127.0.0.1:{}/", port(app)), None::<&str>);
        }
        "start" => spawn_boot(app),
        "stop" => {
            stop_owned(app);
            publish(app, |_| {}); // tells the windows, then refreshes the tray
        }
        "restart" => {
            stop_owned(app);
            spawn_boot(app);
        }
        "quit" => {
            stop_owned(app);
            app.exit(0);
        }
        _ => {}
    }
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_window(app, None)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec![HIDDEN_ARG])))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_positioner::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![shell_state, boot_command, use_port, open_url, api, tray_action,
            pick_folder, set_autostart, open_logs, check_update, install_update])
        .setup(|app| {
            let view = ShellState {
                phase: "checking",
                os: os_name(),
                port: initial_port(app.handle()),
                python_missing: false,
                launch: None,
                error: None,
                autostart: false,
                owned: false,
                version: app.package_info().version.to_string(),
                update: None,
                update_error: None,
            };
            app.manage(AppState(Mutex::new(Shell { python: None, path: None, child: None, view, popover_hidden: None }), Mutex::new(())));
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            let handle = app.handle().clone();
            let view = TrayView {
                text: "OpenGSD Path: starting".into(),
                running: false,
                owned: false,
                attention: false,
                update: None,
                setup: false,
            };
            TrayIconBuilder::with_id(TRAY_ID)
                .icon(tray_icon(false))
                .icon_as_template(cfg!(target_os = "macos"))
                .tooltip(&view.text)
                .menu(&tray_menu(&handle, &view)?)
                // Linux sends no tray click events, so the menu stays on left click there.
                // On macOS and Windows a left click opens the popover; the menu is on right click.
                .show_menu_on_left_click(cfg!(target_os = "linux"))
                .on_menu_event(|app, event| on_menu(app, event.id.as_ref()))
                .on_tray_icon_event(|tray, event| {
                    tauri_plugin_positioner::on_tray_event(tray.app_handle(), &event);
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        toggle_popover(tray.app_handle());
                    }
                })
                .build(app)?;
            let hidden = std::env::args().any(|arg| arg == HIDDEN_ARG);
            if !hidden {
                show_window(&handle, None);
            }
            let first = handle.clone();
            thread::spawn(move || {
                if opens_window_after_boot(hidden, boot(&first).phase) {
                    show_window(&first, None);
                }
            });
            // Look for a newer app version once at start. A development build never updates itself.
            if !cfg!(debug_assertions) {
                let updater = handle.clone();
                tauri::async_runtime::spawn(async move {
                    check_update(updater).await;
                });
            }
            thread::spawn(move || {
                let mut last = view;
                loop {
                    thread::sleep(POLL);
                    let view = tray_view(&handle);
                    if view != last {
                        let (app, shown) = (handle.clone(), view.clone());
                        let _ = handle.run_on_main_thread(move || apply_view(&app, &shown));
                        last = view;
                    }
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| match event {
            // Closing the window keeps the app in the tray.
            WindowEvent::CloseRequested { api, .. } => {
                api.prevent_close();
                let _ = window.hide();
            }
            // The popover closes when the user clicks elsewhere.
            WindowEvent::Focused(false) if window.label() == POPOVER => {
                window.state::<AppState>().0.lock().unwrap().popover_hidden = Some(Instant::now());
                let _ = window.hide();
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("error while building the OpenGSD Path app");
    app.run(|app, event| match event {
        RunEvent::ExitRequested { code: None, api, .. } => api.prevent_exit(),
        // Opening the app again from Finder or Spotlight starts no second process.
        #[cfg(target_os = "macos")]
        RunEvent::Reopen { .. } => show_window(app, None),
        RunEvent::Exit => {
            stop_owned(app);
        }
        _ => {}
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn view() -> ShellState {
        ShellState { phase: "ready", os: "macos", port: 8765, python_missing: false, launch: None, error: None,
            autostart: false, owned: false, version: "0.1.0".into(), update: None, update_error: None }
    }

    #[test]
    fn a_found_update_is_offered_and_clears_an_old_error() {
        let mut state = view();
        state.update_error = Some("network".into());
        let found = UpdateInfo { version: "0.1.1".into(), notes: None };
        checked(&mut state, Ok(Some(found.clone())));
        assert_eq!((state.update, state.update_error), (Some(found), None));
    }

    #[test]
    fn a_failed_check_keeps_the_update_found_before() {
        let mut state = view();
        let found = UpdateInfo { version: "0.1.1".into(), notes: None };
        state.update = Some(found.clone());
        checked(&mut state, Err("network is down".into()));
        assert_eq!((state.update, state.update_error), (Some(found), Some("network is down".into())));
    }

    #[test]
    fn no_newer_version_offers_nothing() {
        let mut state = view();
        state.update = Some(UpdateInfo { version: "0.1.1".into(), notes: None });
        checked(&mut state, Ok(None));
        assert_eq!((state.update, state.update_error), (None, None));
    }

    #[test]
    fn a_refused_install_starts_the_monitor_again_only_when_it_was_stopped() {
        assert_eq!(after_install(Ok(()), true), AfterInstall::Restart);
        assert_eq!(after_install(Err("no space".into()), true),
            AfterInstall::Refused { error: "no space".into(), start_monitor: true });
        assert_eq!(after_install(Err("no space".into()), false),
            AfterInstall::Refused { error: "no space".into(), start_monitor: false });
    }

    #[test]
    fn a_clean_start_carries_the_daemon_command() {
        let launch = json!({"action": "start", "serve_argv": ["py", "-m", "gsd_daemon", "serve"], "problems": []});
        assert_eq!(decide(&launch), Next::Start(vec!["py".into(), "-m".into(), "gsd_daemon".into(), "serve".into()]));
    }

    #[test]
    fn a_current_daemon_is_reused_and_never_started() {
        assert_eq!(decide(&json!({"action": "reuse", "serve_argv": null, "problems": []})), Next::Reuse);
    }

    #[test]
    fn a_blocking_problem_stops_the_start() {
        let launch = json!({"action": "start", "serve_argv": ["py"],
            "problems": [{"kind": "port", "blocking": true}]});
        assert_eq!(decide(&launch), Next::Blocked);
    }

    #[test]
    fn a_note_does_not_stop_the_start() {
        let launch = json!({"action": "start", "serve_argv": ["py"],
            "problems": [{"kind": "autostart", "blocking": false}]});
        assert_eq!(decide(&launch), Next::Start(vec!["py".into()]));
    }

    #[test]
    fn setup_or_a_start_without_a_command_blocks() {
        assert_eq!(decide(&json!({"action": "setup", "problems": []})), Next::Blocked);
        assert_eq!(decide(&json!({"action": "start", "serve_argv": null, "problems": []})), Next::Blocked);
        assert_eq!(decide(&json!({})), Next::Blocked);
    }

    #[test]
    fn autostart_is_turned_on_one_time_and_only_after_a_clean_start() {
        assert!(enables_autostart(true, true, false));
        assert!(!enables_autostart(true, true, true)); // the user may have turned it off since
        assert!(!enables_autostart(true, false, false)); // an old startup entry remains
        assert!(!enables_autostart(false, true, false));
    }

    #[test]
    fn the_click_that_closed_the_popover_does_not_open_it_again() {
        let hidden = Instant::now();
        assert!(closed_by_this_click(Some(hidden), hidden + Duration::from_millis(50)));
        assert!(!closed_by_this_click(Some(hidden), hidden + Duration::from_secs(2)));
        assert!(!closed_by_this_click(None, hidden));
    }

    #[test]
    fn a_start_at_login_opens_the_window_only_for_a_problem() {
        assert!(opens_window_after_boot(true, "blocked"));
        assert!(!opens_window_after_boot(true, "ready"));
        assert!(!opens_window_after_boot(false, "blocked")); // the window is already open
    }

    #[test]
    fn a_child_process_gets_the_refreshed_path() {
        let path_of = |command: Command| {
            command.get_envs().find(|(name, _)| *name == "PATH").map(|(_, value)| value.map(|v| v.to_owned()))
        };
        assert_eq!(path_of(command(&["python3".into()], Some("/opt/bin:/usr/bin"))), Some(Some("/opt/bin:/usr/bin".into())));
        assert_eq!(path_of(command(&["python3".into()], None)), None); // it inherits this process's PATH
    }

    #[test]
    fn the_path_is_read_between_the_marks() {
        assert_eq!(marked_path("motd line\n__PATH__/opt/bin:/usr/bin__PATH__").as_deref(), Some("/opt/bin:/usr/bin"));
        assert_eq!(marked_path("__PATH__C:\\Windows;C:\\Py Launcher__PATH__\r\n").as_deref(), Some("C:\\Windows;C:\\Py Launcher"));
        assert_eq!(marked_path("__PATH____PATH__"), None);
        assert_eq!(marked_path("command not found"), None);
    }

    #[test]
    fn a_project_folder_reaches_the_page_as_one_string_literal() {
        for root in ["/work/gsd-path", "C:\\Users\\me\\my app", "/work/a\"b');alert(1);//\n</script>"] {
            let script = project_script(root);
            let literal = script
                .strip_prefix("location.hash='#/project/'+encodeURIComponent(")
                .and_then(|rest| rest.strip_suffix(")"))
                .expect("the script sets the project route");
            assert_eq!(serde_json::from_str::<String>(literal).unwrap(), root);
        }
    }

    #[test]
    fn requests_only_reach_the_local_daemon() {
        assert_eq!(api_url(8765, "GET", "/status").unwrap(), "http://127.0.0.1:8765/status");
        assert_eq!(api_url(9000, "POST", "/api/refresh").unwrap(), "http://127.0.0.1:9000/api/refresh");
        assert!(api_url(8765, "GET", "status").is_err());
        assert!(api_url(8765, "GET", "@evil.example/").is_err());
        assert!(api_url(8765, "DELETE", "/status").is_err());
    }
}
