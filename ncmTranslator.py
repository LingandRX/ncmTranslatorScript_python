import base64
import binascii
import json
import logging
import os
import struct
import sys
import time
import urllib.request
from os import fspath
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from Crypto.Cipher import AES

music_suffix_list = ['mp3', 'wav', 'ape', 'flac', 'MP3', 'WAV', 'APE', 'FLAC']


# 进行ncm解码
def dump(file_path, file_name_no_suffix):
    core_key = binascii.a2b_hex("687A4852416D736F356B496E62617857")
    meta_key = binascii.a2b_hex("2331346C6A6B5F215C5D2630553C2728")
    unpad = lambda s: s[0:-(s[-1] if isinstance(s[-1], int) else ord(s[-1]))]
    with open(file_path, 'rb') as f:
        header = f.read(8)
        assert binascii.b2a_hex(header) == b'4354454e4644414d'
        f.seek(2, 1)
        key_length = struct.unpack('<I', f.read(4))[0]
        key_data = f.read(key_length)
        key_data = bytes([b ^ 0x64 for b in key_data])
        cryptor = AES.new(core_key, AES.MODE_ECB)
        key_data = unpad(cryptor.decrypt(key_data))[17:]
        key_length = len(key_data)
        key_box = bytearray(range(256))
        c = 0
        last_byte = 0
        key_offset = 0
        for i in range(256):
            swap = key_box[i]
            c = (swap + last_byte + key_data[key_offset]) & 0xff
            key_offset = (key_offset + 1) % key_length
            key_box[i], key_box[c] = key_box[c], swap
            last_byte = c

        meta_length = struct.unpack('<I', f.read(4))[0]
        meta_data = f.read(meta_length)
        meta_data = bytes([b ^ 0x63 for b in meta_data])
        meta_data = base64.b64decode(meta_data[22:])
        cryptor = AES.new(meta_key, AES.MODE_ECB)
        meta_data = unpad(cryptor.decrypt(meta_data)).decode('utf-8')[6:]
        meta_data = json.loads(meta_data)

        f.seek(9, 1)  # 跳过crc32(4字节)和未知5字节
        image_size = struct.unpack('<I', f.read(4))[0]
        image_data = f.read(image_size)

        file_name = file_name_no_suffix + '.' + meta_data['format']
        output_path = os.path.join(os.path.split(file_path)[0], file_name)

        with open(output_path, 'wb') as m:
            while True:
                chunk = bytearray(f.read(0x8000))
                if not chunk:
                    break
                for i in range(len(chunk)):
                    j = (i + 1) & 0xff
                    chunk[i] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xff]) & 0xff]
                m.write(chunk)

    try:
        urllib.request.urlretrieve(meta_data['albumPic'],
                                   os.path.join(os.path.split(file_path)[0], file_name_no_suffix) + '.jpg')
    except Exception as e:
        print('下载专辑图片出错', e)


def file_extension(path):
    return os.path.splitext(path)[-1][1:]


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


def recursion(file_name, root_dir, file_list, tasks):
    full_file = os.path.join(root_dir, file_name)
    if os.path.isfile(full_file):
        if file_extension(full_file) != "ncm":
            print(full_file + ' >>> 非ncm文件, 跳过')
            return
        if file_exist(file_name, file_list, root_dir):
            print(full_file + ' >>> 同名文件已存在, 跳过')
            return
        print(full_file + ' >>> 提交转码任务')
        tasks.append((full_file, file_no_extension(file_name)))
    elif os.path.isdir(full_file):
        print('>>> 进入文件夹: ' + full_file)
        for child in os.listdir(full_file):
            recursion(child, full_file, os.listdir(full_file), tasks)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        rootdir = sys.argv[1]
    else:
        rootdir = fspath(Path(__file__).parent.resolve())
    print('当前需要处理的文件夹路径: ' + rootdir)

    start_time = time.time()
    print('开始处理 ' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

    file_list = os.listdir(rootdir)
    tasks = []
    for file in file_list:
        recursion(file, rootdir, file_list, tasks)

    # 使用多线程池
    futures = []
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        for file_path, no_suffix in tasks:
            futures.append(executor.submit(dump, file_path, no_suffix))

        for future in as_completed(futures):
            try:
                future.result()
                print("任务完成")
            except Exception as e:
                logging.exception("转码任务出错", exc_info=e)

    end_time = time.time()
    print('全部文件处理完成 ' + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    print('处理时间:', end_time - start_time)
