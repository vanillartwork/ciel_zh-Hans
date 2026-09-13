# Gust PAK 封包格式

KTGL 引擎使用的资源封包。Ciel nosurge DX 的封包在 `Res_x64/`：

| 文件 | 大小 | 内容 |
|---|---:|---|
| `PACK00_01.PAK` | 1.7 GB | 贴图、模型、字体图集 |
| `PACK00_02.PAK` | 2.3 GB | 资源 |
| `PACK00_03.PAK` | 1.1 GB | 资源 |
| `PACK01.PAK` | 33 MB | **脚本、界面、数据表**（本地化主要目标） |
| `PACK02.PAK` | 125 KB | 小资源 |

## 结构

```
偏移 0    头部（16 字节）
          u32  version      0x00020000
          u32  nb_files
          u32  header_size  16
          u32  flags

偏移 16   条目表，每条 168 字节（0xA8）
          char name[128]    文件名，加密
          u32  size         解密后的大小
          u8   key[20]      这个条目的异或密钥
          u64  offset       相对数据区起点
          u32  flags
          （填充到 168）

数据区    从 16 + nb_files * 168 开始
```

## 加密

**文件名和文件内容都用同一个 20 字节 key 做循环异或。**

```python
def xor(data, key):
    if not any(key):          # 全零 key = 明文存储
        return data
    k = bytes(key) * (len(data) // 20 + 2)
    return bytes(a ^ b for a, b in zip(data, k))
```

key 全为零时表示这个条目没有加密，直接存储。

文件名解密后是以 `\0` 结尾的 UTF-8，用反斜杠作路径分隔符，
开头通常有一个反斜杠：

```
\inc\event\res\01\ma01_tt01.txt
```

## 重建

重建时**保留每个条目原来的 key**，偏移重新计算。
没有改动的条目重新加密后字节完全相同。

关键实现细节：**保存原始的 `raw_name` 字节，写回时原样使用**，
不要用解密后的名字重新加密。这样即使某个文件名的编码有些古怪，
也不会在往返过程中被改变。

`tools/gustpak.py` 的 `rebuild()` 就是这么做的。
`tools/test_roundtrip.py` 验证：空改动重建出的 `PACK01.PAK`
与原文件 33,781,160 字节完全一致。

## 大文件的处理

`PACK00_01.PAK` 有 1.7 GB。逐字节的 Python 异或太慢，
用大整数一次性异或快得多：

```python
n = len(data)
k = (bytes(key) * (n // 20 + 2))[:n]
out = (int.from_bytes(data, "big") ^ int.from_bytes(k, "big")).to_bytes(n, "big")
```

## 封包里有什么

`PACK01.PAK` 的 3,750 个条目：

| 扩展名 | 数量 | 内容 |
|---|---:|---|
| `.txt` | 3,046 | 剧情脚本（其实是 CSV） |
| `.xml` | 248 | 界面布局 |
| `.bin` | 158 | 数据表（道具、帮助、邮件…） |
| `.inc` | 153 | **编译期生成的 C++ 头文件片段** |
| `.gbd` | 72 | 事件历史数据 |
| 其他 | 73 | `.bas` `.frm` 等开发期残留 |

`.inc` 值得单独说：它们是 Gust 内部工具生成的 C++ 源码片段，
形如

```
{ "食器洗い",  "食器洗い。空の食べ物を流しへ入れる、食器洗い…" },
```

**游戏运行时并不读取它们**，只是随封包一起发布了。
判断某个字符串是不是"引擎按名字查找的键"时，
`.inc` 里出现不算证据；`.bin` 和 `.xml` 里出现才需要警惕。
