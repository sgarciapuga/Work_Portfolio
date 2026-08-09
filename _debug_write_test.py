import os
print('cwd', os.getcwd())
with open('debug_write_test.txt','w', encoding='utf-8') as f:
    f.write('hello')
print('wrote file, exists?', os.path.exists('debug_write_test.txt'))
