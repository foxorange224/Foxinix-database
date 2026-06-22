#!/usr/bin/env python3
"""AES-256-CBC encryption with HMAC-SHA256 authentication and PBKDF2 key derivation."""

import os
import base64
import hashlib
import hmac as hmac_mod
from typing import Optional

PASSWORD = "X9f2-K7wQ-M5pZ-V2tRt-XyZ99"
ITERATIONS = 2000
ICONS_DIR = "icons"
MDS_DIR = "mds"
DATA_FILE = "data.json"

sbox = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]

inv_sbox = [0] * 256
for _i in range(256):
    inv_sbox[sbox[_i]] = _i

rcon = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(i ^ j for i, j in zip(a, b))


def sub_word(word: bytes) -> bytes:
    return bytes(sbox[b] for b in word)


def rot_word(word: bytes) -> bytes:
    return word[1:] + word[:1]


def key_expansion(key: bytes):
    nk = len(key) // 4
    nr = nk + 6
    w = []
    for i in range(nk):
        w.append(key[4*i:4*i+4])
    for i in range(nk, 4 * (nr + 1)):
        temp = w[i-1]
        if i % nk == 0:
            temp = xor_bytes(sub_word(rot_word(temp)), bytes([rcon[i//nk - 1], 0, 0, 0]))
        elif nk > 6 and i % nk == 4:
            temp = sub_word(temp)
        w.append(xor_bytes(w[i-nk], temp))
    return [bytearray(b) for b in w], nr


def add_round_key(state, rk):
    for i in range(4):
        for j in range(4):
            state[j][i] ^= rk[i][j]


def sub_bytes(state):
    for i in range(4):
        for j in range(4):
            state[i][j] = sbox[state[i][j]]


def inv_sub_bytes(state):
    for i in range(4):
        for j in range(4):
            state[i][j] = inv_sbox[state[i][j]]


def shift_rows(state):
    state[1][0], state[1][1], state[1][2], state[1][3] = state[1][1], state[1][2], state[1][3], state[1][0]
    state[2][0], state[2][1], state[2][2], state[2][3] = state[2][2], state[2][3], state[2][0], state[2][1]
    state[3][0], state[3][1], state[3][2], state[3][3] = state[3][3], state[3][0], state[3][1], state[3][2]


def inv_shift_rows(state):
    state[1][0], state[1][1], state[1][2], state[1][3] = state[1][3], state[1][0], state[1][1], state[1][2]
    state[2][0], state[2][1], state[2][2], state[2][3] = state[2][2], state[2][3], state[2][0], state[2][1]
    state[3][0], state[3][1], state[3][2], state[3][3] = state[3][1], state[3][2], state[3][3], state[3][0]


def xtime(a: int) -> int:
    r = (a << 1) & 0xff
    if a & 0x80:
        r ^= 0x1b
    return r


def mix_columns(state):
    for i in range(4):
        a = [state[j][i] for j in range(4)]
        state[0][i] = xtime(a[0]) ^ (xtime(a[1]) ^ a[1]) ^ a[2] ^ a[3]
        state[1][i] = a[0] ^ xtime(a[1]) ^ (xtime(a[2]) ^ a[2]) ^ a[3]
        state[2][i] = a[0] ^ a[1] ^ xtime(a[2]) ^ (xtime(a[3]) ^ a[3])
        state[3][i] = (xtime(a[0]) ^ a[0]) ^ a[1] ^ a[2] ^ xtime(a[3])


def inv_mix_columns(state):
    for i in range(4):
        a = [state[j][i] for j in range(4)]
        state[0][i] = mul(14, a[0]) ^ mul(11, a[1]) ^ mul(13, a[2]) ^ mul(9, a[3])
        state[1][i] = mul(9, a[0]) ^ mul(14, a[1]) ^ mul(11, a[2]) ^ mul(13, a[3])
        state[2][i] = mul(13, a[0]) ^ mul(9, a[1]) ^ mul(14, a[2]) ^ mul(11, a[3])
        state[3][i] = mul(11, a[0]) ^ mul(13, a[1]) ^ mul(9, a[2]) ^ mul(14, a[3])


def mul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xff
        if hi:
            a ^= 0x1b
        b >>= 1
    return p


def bytes_to_state(block: bytes):
    s = [[0]*4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s[j][i] = block[i*4 + j]
    return s


def state_to_bytes(state) -> bytes:
    b = bytearray(16)
    for i in range(4):
        for j in range(4):
            b[i*4 + j] = state[j][i]
    return bytes(b)


def aes_encrypt_block(pt: bytes, rk, nr: int) -> bytes:
    s = bytes_to_state(pt)
    add_round_key(s, rk[0:4])
    for rnd in range(1, nr):
        sub_bytes(s); shift_rows(s); mix_columns(s)
        add_round_key(s, rk[rnd*4:(rnd+1)*4])
    sub_bytes(s); shift_rows(s)
    add_round_key(s, rk[nr*4:(nr+1)*4])
    return state_to_bytes(s)


def aes_decrypt_block(ct: bytes, rk, nr: int) -> bytes:
    s = bytes_to_state(ct)
    add_round_key(s, rk[nr*4:(nr+1)*4])
    for rnd in range(nr - 1, 0, -1):
        inv_shift_rows(s); inv_sub_bytes(s)
        add_round_key(s, rk[rnd*4:(rnd+1)*4])
        inv_mix_columns(s)
    inv_shift_rows(s); inv_sub_bytes(s)
    add_round_key(s, rk[0:4])
    return state_to_bytes(s)


def pkcs7_pad(data: bytes) -> bytes:
    n = 16 - (len(data) % 16)
    return data + bytes([n] * n)


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("Empty data")
    n = data[-1]
    if n < 1 or n > 16:
        raise ValueError(f"Invalid padding byte: {n}")
    if data[-n:] != bytes([n] * n):
        raise ValueError("Invalid PKCS7 padding")
    return data[:-n]


def aes_cbc_encrypt(pt: bytes, key: bytes, iv: bytes) -> bytes:
    padded = pkcs7_pad(pt)
    rk, nr = key_expansion(key)
    prev = iv
    result = bytearray()
    for i in range(0, len(padded), 16):
        b = padded[i:i+16]
        x = xor_bytes(b, prev)
        e = aes_encrypt_block(x, rk, nr)
        result.extend(e)
        prev = e
    return bytes(result)


def aes_cbc_decrypt(ct: bytes, key: bytes, iv: bytes) -> bytes:
    rk, nr = key_expansion(key)
    prev = iv
    result = bytearray()
    for i in range(0, len(ct), 16):
        b = ct[i:i+16]
        d = aes_decrypt_block(b, rk, nr)
        x = xor_bytes(d, prev)
        result.extend(x)
        prev = b
    return pkcs7_unpad(bytes(result))


def derive_key(password: str, salt: bytes, dklen: int = 48) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS, dklen=dklen)


def encrypt_enlace(enlace: str, password: str) -> str:
    salt = os.urandom(16)
    iv = os.urandom(16)
    key = derive_key(password, salt, dklen=48)
    aes_key = key[:32]
    mac_key = key[32:]
    ct = aes_cbc_encrypt(enlace.encode('utf-8'), aes_key, iv)
    mac = hmac_mod.new(mac_key, bytes([2]) + salt + iv + ct, 'sha256').digest()
    payload = bytes([2]) + salt + iv + ct + mac
    return base64.b64encode(payload).decode('ascii')


def decrypt_enlace(encrypted_b64: str, password: str) -> Optional[str]:
    try:
        payload = base64.b64decode(encrypted_b64)
    except Exception:
        return None

    try:
        if payload[0] == 2 and len(payload) >= 81:
            salt = payload[1:17]
            iv = payload[17:33]
            ct = payload[33:-32]
            mac = payload[-32:]
            key = derive_key(password, salt, dklen=48)
            aes_key = key[:32]
            mac_key = key[32:]
            expected_mac = hmac_mod.new(mac_key, bytes([2]) + salt + iv + ct, 'sha256').digest()
            if not hmac_mod.compare_digest(mac, expected_mac):
                return None
            return aes_cbc_decrypt(ct, aes_key, iv).decode('utf-8')
    except Exception:
        pass

    try:
        salt = payload[:16]
        iv = payload[16:32]
        ct = payload[32:]
        key = derive_key(password, salt, dklen=32)
        return aes_cbc_decrypt(ct, key, iv).decode('utf-8')
    except Exception:
        return None


def icon_path(item_id: str) -> str:
    return os.path.join(ICONS_DIR, f'{item_id}.webp')


def md_path(item_id: str) -> str:
    return os.path.join(MDS_DIR, f'{item_id}.md')
