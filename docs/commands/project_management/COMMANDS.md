# Project Management Commands — Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Each command is described in a separate file: purpose, arguments, return format, and examples.

| Command | Description | Doc |
|---------|-------------|-----|
| change_project_id | Change project UUID | [change_project_id.md](change_project_id.md) |
| clear_trash | Permanently delete all contents of trash | [clear_trash.md](clear_trash.md) |
| create_project | Register new project | [create_project.md](create_project.md) |
| delete_project | Remove project and its data (disk → trash) | [delete_project.md](delete_project.md) |
| delete_unwatched_projects | Delete projects not under watch dir | [delete_unwatched_projects.md](delete_unwatched_projects.md) |
| list_projects | List all registered projects | [list_projects.md](list_projects.md) |
| list_trashed_projects | List projects in trash (recycle bin) | [list_trashed_projects.md](list_trashed_projects.md) |
| permanently_delete_from_trash | Permanently delete one folder from trash | [permanently_delete_from_trash.md](permanently_delete_from_trash.md) |
| restore_project_from_trash | Restore a project from trash | [restore_project_from_trash.md](restore_project_from_trash.md) |
| list_watch_dirs | List watch directories | [list_watch_dirs.md](list_watch_dirs.md) |
| run_project_script | Run a Python script in the project venv sandbox | [run_project_script.md](run_project_script.md) |
| run_project_module | Run `python -m <module>` in the project sandbox | [run_project_module.md](run_project_module.md) |
| project_pip_install | `pip install` into **that** project’s `.venv`/`venv` only; always queued (long-running) | [project_pip_install.md](project_pip_install.md) |
| project_pip_list | List packages in the project venv (`pip list` / `pip freeze`; `project_id` required) | [project_pip_list.md](project_pip_list.md) |
| project_pip_show | Show package metadata (`pip show`; `project_id` required) | [project_pip_show.md](project_pip_show.md) |
| project_pip_uninstall | Remove packages (`pip uninstall`; `project_id` required) | [project_pip_uninstall.md](project_pip_uninstall.md) |
| project_pip_check | Presence check from `pip list --format=json` (`project_id` + `packages` required) | [project_pip_check.md](project_pip_check.md) |
| project_pip_search | List/filter **installed** packages only — no PyPI (`project_id` required) | [project_pip_search.md](project_pip_search.md) |

See [README.md](README.md) for block overview.
