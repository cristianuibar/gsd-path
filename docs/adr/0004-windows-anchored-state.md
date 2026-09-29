# Windows creates STATE.md through pinned handles, not dir_fd

Status: accepted. Tracked in #181 and #189.

`detect_project initialize` creates `.project/STATE.md` in a repository that it
has just classified. The repository is not trusted. A clone, an agent, or a
concurrent process can plant a symlink or junction, or swap `.project` between
classification and the write. Any of these could turn the create into a write
outside the repository, or into overwriting a file that is not ours.

On POSIX the create is anchored with `dir_fd`:
- open the root, then open `.project` relative to it with `O_NOFOLLOW |
  O_DIRECTORY`;
- create the temporary file relative to `.project`;
- publish with `link(..., follow_symlinks=False)`, which refuses an existing
  name;
- re-check identities with `samestat` at every step.

Windows has no `dir_fd`, no `O_NOFOLLOW`, and no `O_DIRECTORY`, so
`initialize` used to fail closed there and never wrote STATE.md.

**Decision:** on Windows, the same guarantee comes from Win32 handles
(`write_state_windows`):

- **Pin, don't re-resolve.** The root is opened with `CreateFileW(...,
  FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT)`, and without
  `FILE_SHARE_DELETE`. While that handle is open, nobody can rename or delete
  the directory, so it cannot be replaced. `.project` is created or opened the
  same way, relative to the root handle.
- **Relative opens.** `.project` and the temporary file are opened with
  `NtCreateFile` and `OBJECT_ATTRIBUTES.RootDirectory` set to the pinned parent,
  which is the `openat` equivalent. No path is resolved again after it has
  been checked.
- **No following.** Every open uses `FILE_OPEN_REPARSE_POINT`. A junction or
  symlink therefore opens as itself, and the existing `is_link_like` check
  (the name-surrogate reparse bit) rejects it. `FILE_DIRECTORY_FILE` and
  `FILE_NON_DIRECTORY_FILE` replace `O_DIRECTORY`.
- **Exclusive temporary file.** The temporary file is opened with share mode 0,
  so no other process can open it while it is held. `FILE_OPEN_IF` reuses a
  leftover regular temporary file, as POSIX does.
- **No-replace publish.** `NtSetInformationFile(FileRenameInformation,
  ReplaceIfExists=FALSE, RootDirectory=.project)` renames the temporary file's
  own handle. It fails if `STATE.md` already exists in any form.
- **Handle rollback.** On failure the file is marked delete-on-close through
  our handle (`FileDispositionInfo`). The rollback can therefore only delete
  the file we created, whatever its name is by then.
- **Same identity checks.** `os.fstat` on the adopted descriptors fills in
  `st_dev`, `st_ino`, and `st_nlink`. The POSIX `samestat` and link-count
  checks run unchanged.
- **Same lock.** The create holds `_common.directory_mutex(.project)`, the
  named kernel mutex that `pipeline_state` holds for this track on Windows.

`STATE_CREATE_SUPPORTED` is true on both platforms, so `classify` also accepts
a leftover temporary file on Windows, which lets an interrupted create resume.

**Consequences:**
- `initialize` works on native Windows. `tests/test_detect_project_windows.py`
  checks that each attack is refused or has no effect: a junction at
  `.project`, renaming `.project` mid-write (blocked by the pin), a symlink at
  `STATE.md`, rollback, and an existing `STATE.md`.
- Evidence reads during `classify` still use the `lstat`, open, `fstat`
  fallback on Windows. That fallback detects a swapped final file. It does not
  detect a parent directory that is swapped for a junction before the final
  `lstat`, which could let classification read one file outside the repository.
  Moving evidence reads onto the same pinned handles is a follow-up. Reads
  never write, so this does not weaken the create guarantee.
- The code depends on `ntdll` through `ctypes`. `NtCreateFile` and
  `NtSetInformationFile` are documented and stable since Windows XP.
