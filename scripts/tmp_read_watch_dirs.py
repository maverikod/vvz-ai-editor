with open('/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/database/watch_dirs.py') as f:
    src = f.read()
start = src.find('def update_watch_dir_path')
end = src.find('def get_watch_dir_path')
print(src[start:end])
print('---vectorization watch_dirs---')
with open('/home/vasilyvz/projects/tools/ai_editor/ai_editor/core/vectorization_worker_pkg/watch_dirs.py') as f:
    src2 = f.read()
start2 = src2.find('def _refresh_config')
print(src2[start2:])
