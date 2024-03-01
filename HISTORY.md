## 20240204

- Improve copy semantics. See copy() function documentation.
  - copy(file, destination_file=None): copy file to destination_file (or target output path/file.name).
  - copy(files, destination_folder=None): copy files to destination_folder (or target output path).
  - copy(folder, destination_folder=None): mirror folder to destination_folder (or target output path).
- Disable import statement.
- Make file marker optional.
- Detect/warn/error on assignment of variables to common functions/keywords(target(), path(), etc). 
  - e.g. `target=True` should not be possible.
- Unify the exception hierarchy.
- Rename Runnable to Action.
- Skip None values in path and argument lists.
- Add flag to enable Target.path option.
