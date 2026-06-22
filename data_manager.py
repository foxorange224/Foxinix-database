#!/usr/bin/env python3
"""Data manager for FoxWeb database — load, save, CRUD, reorder, icons, markdown."""

import os
import json
import logging
from typing import Optional, Any

from crypto_utils import (
    DATA_FILE, ICONS_DIR, MDS_DIR, PASSWORD,
    encrypt_enlace, decrypt_enlace, icon_path, md_path,
)

logger = logging.getLogger(__name__)


class DataManager:
    DEFAULT_CATEGORIES = ['programas', 'sistemas', 'juegos', 'apks', 'extras']

    def __init__(self):
        self.data: dict[str, list[dict[str, Any]]] = {}
        self.categories_order: list[str] = list(self.DEFAULT_CATEGORIES)
        self._id_counter: int = 0
        self.modified: bool = False
        self.password: str = PASSWORD
        self._icon_cache: dict[str, Any] = {}

    def load(self) -> bool:
        if not os.path.exists(DATA_FILE):
            return False
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load %s: %s", DATA_FILE, e)
            return False

        self.data = {}
        loaded = 0
        for cat in self.categories_order:
            if cat in raw:
                self.data[cat] = self._decrypt_items(raw[cat])
                loaded += len(self.data[cat])
        for cat in raw:
            if cat not in self.data:
                self.data[cat] = self._decrypt_items(raw[cat])
                loaded += len(self.data[cat])
                if cat not in self.categories_order:
                    self.categories_order.append(cat)

        self._update_id_counter()
        self._icon_cache.clear()
        self.modified = False
        logger.info("Loaded %d items from %s", loaded, DATA_FILE)
        return True

    def save(self) -> bool:
        output = {}
        for cat in self.categories_order:
            if cat not in self.data:
                continue
            output[cat] = self._encrypt_items(self.data[cat])
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            self.modified = False
            logger.info("Saved %d categories", len(output))
            return True
        except IOError as e:
            logger.error("Failed to save %s: %s", DATA_FILE, e)
            return False

    def _decrypt_items(self, items: list[dict]) -> list[dict]:
        result = []
        for item in items:
            d = dict(item)
            if d.get('enlace') and self._is_encrypted(d['enlace']):
                decrypted = decrypt_enlace(d['enlace'], self.password)
                if decrypted is not None:
                    d['enlace'] = decrypted
                else:
                    logger.warning("Failed to decrypt enlace for item %s", d.get('id'))
            d.pop('modal', None)
            result.append(d)
        return result

    def _encrypt_items(self, items: list[dict]) -> list[dict]:
        result = []
        for item in items:
            e = dict(item)
            enl = e.get('enlace', '')
            if enl and enl != '#' and not self._is_encrypted(enl):
                try:
                    e['enlace'] = encrypt_enlace(enl, self.password)
                except Exception as exc:
                    logger.error("Failed to encrypt enlace for item %s: %s", e.get('id'), exc)
            e.pop('modal', None)
            result.append(e)
        return result

    def _is_encrypted(self, val: str) -> bool:
        if not val or val == '#':
            return False
        if val.startswith('http://') or val.startswith('https://'):
            return False
        if len(val) < 40:
            return False
        return True

    def _update_id_counter(self):
        max_id = 0
        for cat in self.data.values():
            for item in cat:
                try:
                    max_id = max(max_id, int(item.get('id', '0')))
                except (ValueError, TypeError):
                    pass
        self._id_counter = max_id + 1

    def get_item(self, cat: str, idx: int) -> Optional[dict]:
        if cat not in self.data or idx < 0 or idx >= len(self.data[cat]):
            return None
        return self.data[cat][idx]

    def add_item(self, cat: str) -> Optional[str]:
        if cat not in self.data:
            return None
        new_id = f'{self._id_counter:06d}'
        self._id_counter += 1
        self.data[cat].append({
            'name': 'Nuevo elemento', 'icon': '', 'info': '',
            'enlace': '#', 'badges': [], 'id': new_id,
        })
        self.modified = True
        logger.info("Added item %s in %s", new_id, cat)
        return new_id

    def delete_item(self, cat: str, idx: int) -> bool:
        if cat not in self.data or idx < 0 or idx >= len(self.data[cat]):
            return False
        entry = self.data[cat][idx]
        item_id = entry.get('id', '')

        ip = icon_path(item_id)
        if os.path.exists(ip):
            os.remove(ip)
        mp = md_path(item_id)
        if os.path.exists(mp):
            os.remove(mp)

        del self.data[cat][idx]
        self._icon_cache.pop(item_id, None)
        self.modified = True
        logger.info("Deleted item %s from %s", item_id, cat)
        return True

    def move_up(self, cat: str, idx: int) -> Optional[int]:
        if cat not in self.data or idx <= 0 or idx >= len(self.data[cat]):
            return None
        items = self.data[cat]
        items[idx], items[idx - 1] = items[idx - 1], items[idx]
        self.modified = True
        return idx - 1

    def move_down(self, cat: str, idx: int) -> Optional[int]:
        if cat not in self.data or idx < 0 or idx >= len(self.data[cat]) - 1:
            return None
        items = self.data[cat]
        items[idx], items[idx + 1] = items[idx + 1], items[idx]
        self.modified = True
        return idx + 1

    def update_item(self, cat: str, idx: int, **kwargs) -> bool:
        item = self.get_item(cat, idx)
        if item is None:
            return False
        for key, val in kwargs.items():
            item[key] = val
        self.modified = True
        return True

    def reorder_ids(self) -> dict[str, str]:
        flat = []
        for cat in self.categories_order:
            if cat not in self.data:
                continue
            for item in self.data[cat]:
                flat.append((cat, item))

        def sort_key(x):
            cat_idx = self.categories_order.index(x[0])
            try:
                id_num = int(x[1].get('id', '0'))
            except (ValueError, TypeError):
                id_num = 0
            return (cat_idx, id_num)

        flat.sort(key=sort_key)

        mapping = {}
        for new_idx, (cat, item) in enumerate(flat, 1):
            old_id = item.get('id', '')
            new_id = f'{new_idx:06d}'
            mapping[old_id] = new_id
            item['id'] = new_id

        for old_id, new_id in mapping.items():
            if old_id == new_id:
                continue
            old_icon = icon_path(old_id)
            new_icon = icon_path(new_id)
            if os.path.exists(old_icon):
                os.rename(old_icon, new_icon)
            old_md = md_path(old_id)
            new_md = md_path(new_id)
            if os.path.exists(old_md):
                os.rename(old_md, new_md)
            self._icon_cache.pop(old_id, None)

        self._update_id_counter()
        self.modified = True
        logger.info("Reordered %d IDs", len(mapping))
        return mapping

    def set_icon(self, item_id: str, source_path: str) -> bool:
        from PIL import Image
        try:
            img = Image.open(source_path).convert('RGBA')
            w, h = img.size
            if w > 180 or h > 180:
                ratio = min(180 / w, 180 / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            os.makedirs(ICONS_DIR, exist_ok=True)
            out = icon_path(item_id)
            img.save(out, 'WEBP', quality=85)
            self._icon_cache.pop(item_id, None)
            return True
        except Exception as e:
            logger.error("Failed to set icon for %s: %s", item_id, e)
            return False

    def remove_icon(self, item_id: str) -> bool:
        ip = icon_path(item_id)
        if os.path.exists(ip):
            os.remove(ip)
        self._icon_cache.pop(item_id, None)
        return True

    def fix_icons(self) -> int:
        from PIL import Image
        if not os.path.isdir(ICONS_DIR):
            return 0
        fixed = 0
        for fname in sorted(os.listdir(ICONS_DIR)):
            path = os.path.join(ICONS_DIR, fname)
            if not os.path.isfile(path):
                continue
            try:
                img = Image.open(path)
                w, h = img.size
                needs_resize = w > 180 or h > 180
                needs_convert = img.format != 'WEBP'
                if not needs_resize and not needs_convert:
                    continue
                if img.mode not in ('RGBA', 'LA'):
                    img = img.convert('RGBA')
                if needs_resize:
                    r = min(180 / w, 180 / h)
                    img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
                img.save(path, 'WEBP', quality=85)
                fixed += 1
            except Exception:
                pass
        self._icon_cache.clear()
        logger.info("Fixed %d icons", fixed)
        return fixed

    def get_icon_pixmap(self, item_id: str, size: int = 180):
        from PyQt5 import QtGui, QtCore
        if item_id in self._icon_cache:
            pix = self._icon_cache[item_id]
            if pix and not pix.isNull():
                return pix.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        path = icon_path(item_id)
        if not os.path.exists(path):
            return None

        try:
            from PIL import Image as PilImage
            pil_img = PilImage.open(path).convert('RGBA')
            data = pil_img.tobytes('raw', 'RGBA')
            qimg = QtGui.QImage(data, pil_img.width, pil_img.height, QtGui.QImage.Format_RGBA8888)
            pix = QtGui.QPixmap.fromImage(qimg)
            if not pix.isNull():
                scaled = pix.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                self._icon_cache[item_id] = pix
                return scaled
        except Exception:
            pass
        return None

    def get_icon_info(self, item_id: str) -> str:
        path = icon_path(item_id)
        if not os.path.exists(path):
            return f'No hay icono para {item_id}'
        try:
            from PIL import Image
            img = Image.open(path)
            return f'Icono: {item_id}.webp ({img.width}x{img.height})'
        except Exception:
            return f'Icono: {item_id}.webp'

    def load_md(self, item_id: str) -> Optional[str]:
        path = md_path(item_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error("Failed to load MD %s: %s", item_id, e)
            return None

    def save_md(self, item_id: str, content: str) -> bool:
        os.makedirs(MDS_DIR, exist_ok=True)
        try:
            with open(md_path(item_id), 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error("Failed to save MD %s: %s", item_id, e)
            return False

    def delete_md(self, item_id: str) -> bool:
        path = md_path(item_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
