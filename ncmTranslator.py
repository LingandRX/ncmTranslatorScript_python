import base64
import binascii
import json
import logging
import os
import struct
import sys
import time
import urllib
from os import fspath
from pathlib import Path

from Crypto.Cipher import AES

music_suffix_list = ['mp3', 'wav', 'ape', 'flac', 'MP3', 'WAV', 'APE', 'FLAC']


# 进行ncm解码
def dump(file_path, file_name_no_suffix):
    core_key = binascii.a2b_hex("687A4852416D736F356B496E62617857")
    meta_key = binascii.a2b_hex("2331346C6A6B5F215C5D2630553C2728")
    unpad = lambda s: s[0:-(s[-1] if type(s[-1]) == int else ord(s[-1]))]
    f = open(file_path, 'rb')
    header = f.read(8)
    assert binascii.b2a_hex(header) == b'4354454e4644414d'
    f.seek(2, 1)
    key_length = f.read(4)
    key_length = struct.unpack('<I', bytes(key_length))[0]
    key_data = f.read(key_length)
    key_data_array = bytearray(key_data)
    for i in range(0, len(key_data_array)): key_data_array[i] ^= 0x64
    key_data = bytes(key_data_array)
    cryptor = AES.new(core_key, AES.MODE_ECB)
    key_data = unpad(cryptor.decrypt(key_data))[17:]
    key_length = len(key_data)
    key_data = bytearray(key_data)
    key_box = bytearray(range(256))
    c = 0
    last_byte = 0
    key_offset = 0
    for i in range(256):
        swap = key_box[i]
        c = (swap + last_byte + key_data[key_offset]) & 0xff
        key_offset += 1
        if key_offset >= key_length: key_offset = 0
        key_box[i] = key_box[c]
        key_box[c] = swap
        last_byte = c
    meta_length = f.read(4)
    meta_length = struct.unpack('<I', bytes(meta_length))[0]
    meta_data = f.read(meta_length)
    meta_data_array = bytearray(meta_data)
    for i in range(0, len(meta_data_array)): meta_data_array[i] ^= 0x63
    meta_data = bytes(meta_data_array)
    meta_data = base64.b64decode(meta_data[22:])
    cryptor = AES.new(meta_key, AES.MODE_ECB)
    meta_data = unpad(cryptor.decrypt(meta_data)).decode('utf-8')[6:]
    meta_data = json.loads(meta_data)
    crc32 = f.read(4)
    crc32 = struct.unpack('<I', bytes(crc32))[0]
    f.seek(5, 1)
    image_size = f.read(4)
    image_size = struct.unpack('<I', bytes(image_size))[0]
    image_data = f.read(image_size)
    file_name = file_name_no_suffix + '.' + meta_data['format']

    ## delete
    # try:
    #     os.remove(os.path.join(os.path.split(file_path)[0], meta_data['musicName'] + '.' + meta_data['format']))
    #     print('删除文件 :' + os.path.join(os.path.split(file_path)[0], meta_data['musicName'] + '.' + meta_data['format']))
    #     ## delete
    # except Exception as e:
    #     print('删除失败', e)

    m = open(os.path.join(os.path.split(file_path)[0], file_name), 'wb')
    chunk = bytearray()
    while True:
        chunk = bytearray(f.read(0x8000))
        chunk_length = len(chunk)
        if not chunk:
            break
        for i in range(1, chunk_length + 1):
            j = i & 0xff
            chunk[i - 1] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xff]) & 0xff]
        m.write(chunk)
    m.close()
    f.close()
    try:
        urllib.request.urlretrieve(meta_data['albumPic'],
                                   os.path.join(os.path.split(file_path)[0], file_name_no_suffix) + '.jpg')
    except Exception as e:
        print('下载专辑图片出错', e)


def file_extension(path):
    filename = os.path.basename(path)
    parts = filename.split('.')
    if len(parts) <= 1:
        return ''
    return parts[-1]


def file_no_extension(path):
    filename = os.path.basename(path)
    if not filename or filename.startswith('.'):
        return filename
    return os.path.splitext(filename)[0]


def file_exist(file_name, file_list, file_list_path):
    base_name = file_no_extension(file_name)
    for file in file_list:
        if os.path.isdir(os.path.join(file_list_path, file)):
            continue
        for suffix in music_suffix_list:
            if (base_name + "." + suffix) == file:
                return True
    return False


def recursion(file_name, root_dir, file_list):
    full_file = os.path.join(root_dir, file_name)
    if os.path.isfile(full_file):
        if file_extension(full_file) != "ncm":
            print(full_file + '>>>>>>>>>>>>>>> 非ncm文件, 跳过')
            return
        if file_exist(file_name, file_list, root_dir):
            print(full_file + '>>>>>>>>>>>>>>> 同名文件跳过')
            return
        try:
            print(full_file + '>>>>>>>>>>>>>>> 开始转码文件')
            dump(full_file, file_no_extension(file_name))
            print(full_file + '>>>>>>>>>>>>>>> 转码文件成功')
        except Exception as err:
            print('转码文件失败: ' + full_file + ' error: ' + err)
    elif os.path.isdir(full_file):
        print('>>>>>>>>>>>>>>> 处理当前文件夹内容: ' + full_file)
        list = os.listdir(full_file)
        for i in range(0, len(list)):
            recursion(list[i], full_file, list)


if __name__ == '__main__':

    if len(sys.argv) > 1:
        # 根据命令的文件夹进行处理
        rootdir = sys.argv[1]
    else:
        # 根据当前所在文件夹进行处理
        rootdir = fspath(Path(__file__).parent.resolve())
    print('当前需要处理的文件夹路径: ' + rootdir)

    start_time = time.time()
    print('开始处理中' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    # 获取rootdir的所有文件名称
    file_list = os.listdir(rootdir)
    for i in range(0, len(file_list)):
        try:
            recursion(file_list[i], rootdir, file_list)
        except Exception as e:
            print('递归处理出现错误')
            logging.exception(e)

    end_time = time.time()
    print('全部文件处理完成 ' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print('处理时间:', end_time - start_time)
