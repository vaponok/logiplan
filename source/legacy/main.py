"""
Combined Foxhole Tools — главное окно с вкладками.

Объединяет:
- Распределитель ресурсов (resource_splitter.ResourceSplitter)
- Написание квоты (quota_writer.MainWindow)
- Таймеры складов (warehouse_timer.WarehouseTimerWidget)

Запуск: python main.py
"""
import os
import sys
import logging

from PyQt5 import QtCore, QtGui, QtWidgets

import i18n

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def resource_path(relative_path):
    """Путь к ресурсу. Работает и в dev-режиме, и в PyInstaller-сборке."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def make_flag_pixmap(kind, w=34, h=24):
    """Рисует флаг (RU/EN/FR) как QPixmap — без внешних файлов-картинок."""
    pix = QtGui.QPixmap(w, h)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

    if kind == "ru":
        stripe = h / 3.0
        for i, color in enumerate(("#ffffff", "#0039A6", "#D52B1E")):
            painter.fillRect(QtCore.QRectF(0, i * stripe, w, stripe + 0.5), QtGui.QColor(color))
    elif kind == "fr":
        stripe = w / 3.0
        for i, color in enumerate(("#0055A4", "#ffffff", "#EF4135")):
            painter.fillRect(QtCore.QRectF(i * stripe, 0, stripe + 0.5, h), QtGui.QColor(color))
    elif kind == "en":
        painter.fillRect(QtCore.QRectF(0, 0, w, h), QtGui.QColor("#00247D"))
        pen = QtGui.QPen(QtGui.QColor("#ffffff")); pen.setWidthF(h * 0.30)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(0, 0), QtCore.QPointF(w, h))
        painter.drawLine(QtCore.QPointF(0, h), QtCore.QPointF(w, 0))
        pen.setColor(QtGui.QColor("#CF142B")); pen.setWidthF(h * 0.12)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(0, 0), QtCore.QPointF(w, h))
        painter.drawLine(QtCore.QPointF(0, h), QtCore.QPointF(w, 0))
        pen.setColor(QtGui.QColor("#ffffff")); pen.setWidthF(h * 0.40)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(w / 2, 0), QtCore.QPointF(w / 2, h))
        painter.drawLine(QtCore.QPointF(0, h / 2), QtCore.QPointF(w, h / 2))
        pen.setColor(QtGui.QColor("#CF142B")); pen.setWidthF(h * 0.20)
        painter.setPen(pen)
        painter.drawLine(QtCore.QPointF(w / 2, 0), QtCore.QPointF(w / 2, h))
        painter.drawLine(QtCore.QPointF(0, h / 2), QtCore.QPointF(w, h / 2))

    painter.end()
    return pix


# === Импорт виджетов ===
from resource_splitter import ResourceSplitter

try:
    from quota_writer import MainWindow as QuotaWriterWidget
except Exception as _e:
    logger.warning(f"quota_writer не загружен: {_e}")
    QuotaWriterWidget = None

try:
    from warehouse_timer import WarehouseTimerWidget
except Exception as _e:
    logger.warning(f"warehouse_timer не загружен: {_e}")
    WarehouseTimerWidget = None


# === TabBar с динамической шириной (как было в scanner_app) ===
class DynamicTabBar(QtWidgets.QTabBar):
    def tabSizeHint(self, index: int) -> QtCore.QSize:
        fm = self.fontMetrics()
        text = self.tabText(index)
        base_w = int(fm.horizontalAdvance(text) * 1.35) + 20
        if index == self.currentIndex():
            base_w += int(base_w * 0.20)
        base_h = fm.height() + 18
        return QtCore.QSize(base_w, base_h)


# === Кастомный заголовок окна с кнопками min/max/close ===
class TitleBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self.setFixedHeight(64)
        self.setObjectName("customTitleBar")
        self.setStyleSheet("""
            QWidget#customTitleBar {
                background-color: #ffffff;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border: none;
            }
        """)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setFixedSize(28, 28)
        layout.addWidget(self.icon_label)

        layout.addStretch()

        def make_btn(text, tooltip):
            b = QtWidgets.QPushButton(text)
            b.setFixedSize(36, 28)
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            b.setToolTip(tooltip)
            b.setFocusPolicy(QtCore.Qt.NoFocus)
            b.setStyleSheet("""
                QPushButton {
                    border-radius: 6px;
                    padding: 0px;
                    font-weight: 700;
                    border: 3px solid #000;
                    background-color: #0066FF;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #1a7bff;
                }
                QPushButton:pressed {
                    background-color: #0047b3;
                }
            """)
            return b

        self.min_btn = make_btn("─", "Свернуть")
        self.max_btn = make_btn("", "Развернуть")
        self.close_btn = make_btn("✕", "Закрыть")

        # Иконка квадрата для кнопки развернуть
        pix = QtGui.QPixmap(20, 20)
        pix.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pix)
        pen = QtGui.QPen(QtGui.QColor("white"), 2)
        painter.setPen(pen)
        painter.drawRect(2, 2, 16, 16)
        painter.end()
        icon = QtGui.QIcon(pix)
        self.max_btn.setIcon(icon)
        self.max_btn.setIconSize(QtCore.QSize(20, 20))

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

        if self._parent_window:
            self.min_btn.clicked.connect(lambda: self._parent_window.showMinimized())
            self.max_btn.clicked.connect(self.toggle_max_restore)
            self.close_btn.clicked.connect(lambda: self._parent_window.close())

        self._is_max = False

    def toggle_max_restore(self):
        if not self._parent_window:
            return
        if self._is_max:
            self._parent_window.showNormal()
            self._is_max = False
        else:
            self._parent_window.showMaximized()
            self._is_max = True

    def mousePressEvent(self, ev):
        if ev.button() == QtCore.Qt.LeftButton:
            self._drag_pos = ev.globalPos()
            self._start_geom = self._parent_window.geometry()

    def mouseMoveEvent(self, ev):
        if hasattr(self, "_drag_pos") and ev.buttons() & QtCore.Qt.LeftButton:
            if self._parent_window.isMaximized():
                # тянем развёрнутое окно — выходим из maximized и продолжаем drag
                ratio = ev.pos().x() / max(1, self.width())
                self._parent_window.showNormal()
                self._is_max = False
                g = self._parent_window.geometry()
                self._parent_window.move(ev.globalPos().x() - int(g.width() * ratio),
                                         ev.globalPos().y() - ev.pos().y())
                self._drag_pos = ev.globalPos()
                self._start_geom = self._parent_window.geometry()
                return
            delta = ev.globalPos() - self._drag_pos
            new_pos = self._start_geom.topLeft() + delta
            self._parent_window.move(new_pos)


# === Главное окно приложения ===
class AppWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.lang = "ru"
        self._force_quit = False
        self.setWindowTitle("Combined Foxhole Tools")
        self.resize(1400, 1000)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.title_bar = TitleBar(self)

        # --- Вкладка 1: Распределитель ---
        self.splitter = ResourceSplitter()

        # Прокручиваемый контейнер для распределителя
        splitter_container = QtWidgets.QWidget()
        splitter_container.setObjectName("mainCanvas")
        sl = QtWidgets.QVBoxLayout(splitter_container)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self.splitter)

        splitter_scroll = QtWidgets.QScrollArea()
        splitter_scroll.setWidgetResizable(True)
        splitter_scroll.setWidget(splitter_container)

        # --- Вкладка 2: Написание квоты ---
        if QuotaWriterWidget is not None:
            try:
                self.quota_widget = QuotaWriterWidget()
            except Exception as e:
                logger.exception(f"Ошибка создания QuotaWriter: {e}")
                self.quota_widget = QtWidgets.QWidget()
                l = QtWidgets.QVBoxLayout(self.quota_widget)
                l.addWidget(QtWidgets.QLabel(i18n.tr("err_quota_writer_create", self.lang, e=e)))
        else:
            self.quota_widget = QtWidgets.QWidget()
            l = QtWidgets.QVBoxLayout(self.quota_widget)
            l.addWidget(QtWidgets.QLabel(i18n.tr("err_quota_writer_missing", self.lang)))

        # --- Вкладка 3: Таймеры складов ---
        if WarehouseTimerWidget is not None:
            try:
                self.timer_widget = WarehouseTimerWidget()
            except Exception as e:
                logger.exception(f"Ошибка создания таймеров: {e}")
                self.timer_widget = QtWidgets.QWidget()
                l = QtWidgets.QVBoxLayout(self.timer_widget)
                l.addWidget(QtWidgets.QLabel(i18n.tr("err_timer_create", self.lang, e=e)))
        else:
            self.timer_widget = QtWidgets.QWidget()
            l = QtWidgets.QVBoxLayout(self.timer_widget)
            l.addWidget(QtWidgets.QLabel(i18n.tr("err_timer_missing", self.lang)))

        # --- StackedWidget для переключения вкладок ---
        stacked = QtWidgets.QStackedWidget()
        stacked.addWidget(splitter_scroll)
        stacked.addWidget(self.quota_widget)
        stacked.addWidget(self.timer_widget)
        self.stacked = stacked

        # --- TabBar в title_bar ---
        self.dynamic_tb = DynamicTabBar()
        self.dynamic_tb.addTab(i18n.tr("tab_splitter", self.lang))
        self.dynamic_tb.addTab(i18n.tr("tab_quota", self.lang))
        self.dynamic_tb.addTab(i18n.tr("tab_timers", self.lang))
        self.dynamic_tb.currentChanged.connect(stacked.setCurrentIndex)
        self.dynamic_tb.currentChanged.connect(lambda idx: self.dynamic_tb.updateGeometry())

        layout = self.title_bar.layout()
        spacer = QtWidgets.QSpacerItem(50, 0, QtWidgets.QSizePolicy.Fixed,
                                       QtWidgets.QSizePolicy.Minimum)
        layout.insertItem(1, spacer)
        layout.insertWidget(2, self.dynamic_tb)

        # --- Переключатель языка (флаги) — справа от вкладок ---
        flags_widget = QtWidgets.QWidget()
        flags_layout = QtWidgets.QHBoxLayout(flags_widget)
        flags_layout.setContentsMargins(10, 0, 0, 0)
        flags_layout.setSpacing(6)

        self.lang_buttons = {}
        lang_group = QtWidgets.QButtonGroup(self)
        lang_group.setExclusive(True)
        flag_style = """
            QPushButton {
                border-radius: 5px;
                border: 2px solid #000;
                padding: 0px;
                background-color: transparent;
            }
            QPushButton:checked {
                border: 3px solid #0066FF;
            }
            QPushButton:hover {
                border-color: #1a7bff;
            }
        """
        for code, tooltip_key in (("ru", "lang_ru_tooltip"), ("en", "lang_en_tooltip"), ("fr", "lang_fr_tooltip")):
            btn = QtWidgets.QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(38, 26)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            btn.setFocusPolicy(QtCore.Qt.NoFocus)
            btn.setIcon(QtGui.QIcon(make_flag_pixmap(code, 34, 22)))
            btn.setIconSize(QtCore.QSize(34, 22))
            btn.setStyleSheet(flag_style)
            btn.setToolTip(i18n.tr(tooltip_key, self.lang))
            btn.clicked.connect(lambda _checked, c=code: self.set_app_language(c))
            lang_group.addButton(btn)
            flags_layout.addWidget(btn)
            self.lang_buttons[code] = btn
        self.lang_buttons["ru"].setChecked(True)

        layout.insertWidget(3, flags_widget)

        # --- Центральный виджет ---
        central = QtWidgets.QWidget()
        central.setObjectName("centralWidget")
        central_layout = QtWidgets.QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.title_bar)
        central_layout.addWidget(stacked)
        self.setCentralWidget(central)

        self.setStyleSheet("""
            QMainWindow {
                background-color: transparent;
            }
            QWidget#centralWidget {
                background-color: #ffffff;
                border: none;
                border-radius: 16px;
            }
            QWidget#customTitleBar {
                background-color: #ffffff;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
                border: none;
            }
            QStackedWidget {
                border: none;
                background: #ffffff;
                padding: 8px;
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }
            QTabBar::tab {
                background: #0066FF;
                color: white;
                border: 3px solid #000;
                border-bottom-color: #0066FF;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 8px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #0047b3;
                border-bottom-color: #0047b3;
                font-weight: 800;
            }
            QWidget#mainCanvas {
                background: #ffffff;
                border: 3px solid #000;
                border-radius: 12px;
                padding: 8px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 18px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #0066FF;
                border: 3px solid #000;
                min-height: 30px;
                border-radius: 9px;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 18px;
            }
            QScrollBar::handle:horizontal {
                background: #0066FF;
                border: 3px solid #000;
                min-width: 30px;
                border-radius: 9px;
            }
        """)

    def set_app_language(self, lang):
        """Переключить язык всего приложения: вкладки, вложенные виджеты, трей."""
        if lang not in i18n.LANGS or lang == self.lang:
            # Даже если язык не поменялся, синхронизируем состояние кнопок-флагов
            if lang in self.lang_buttons:
                self.lang_buttons[lang].setChecked(True)
            return
        self.lang = lang

        # Кнопки-флаги: отметить активную, обновить тултипы
        for code, btn in self.lang_buttons.items():
            btn.setChecked(code == lang)
            tooltip_key = {"ru": "lang_ru_tooltip", "en": "lang_en_tooltip", "fr": "lang_fr_tooltip"}[code]
            btn.setToolTip(i18n.tr(tooltip_key, lang))

        # Названия вкладок
        self.dynamic_tb.setTabText(0, i18n.tr("tab_splitter", lang))
        self.dynamic_tb.setTabText(1, i18n.tr("tab_quota", lang))
        self.dynamic_tb.setTabText(2, i18n.tr("tab_timers", lang))
        self.dynamic_tb.updateGeometry()

        # Кнопки заголовка окна
        self.title_bar.min_btn.setToolTip(i18n.tr("btn_minimize", lang))
        self.title_bar.max_btn.setToolTip(i18n.tr("btn_maximize", lang))
        self.title_bar.close_btn.setToolTip(i18n.tr("btn_close", lang))

        # Вложенные виджеты вкладок
        for widget in (self.splitter, self.quota_widget, self.timer_widget):
            if hasattr(widget, "set_language"):
                widget.set_language(lang)

        # Системный трей
        tray = getattr(self, "_sys_tray_icon", None)
        if tray is not None:
            menu = tray.contextMenu()
            actions = menu.actions() if menu else []
            if len(actions) >= 2:
                actions[0].setText(i18n.tr("tray_open", lang))
                actions[1].setText(i18n.tr("tray_quit", lang))

    # --- ресайз безрамочного окна за края (Windows) ---
    _RESIZE_MARGIN = 8

    def nativeEvent(self, eventType, message):
        if sys.platform == "win32" and eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084 and not self.isMaximized():  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                pos = self.mapFromGlobal(QtCore.QPoint(x, y))
                w, h, m = self.width(), self.height(), self._RESIZE_MARGIN
                left, right = pos.x() < m, pos.x() > w - m
                top, bottom = pos.y() < m, pos.y() > h - m
                hit = {
                    (True, False, True, False): 13,   # HTTOPLEFT
                    (False, True, True, False): 14,   # HTTOPRIGHT
                    (True, False, False, True): 16,   # HTBOTTOMLEFT
                    (False, True, False, True): 17,   # HTBOTTOMRIGHT
                    (True, False, False, False): 10,  # HTLEFT
                    (False, True, False, False): 11,  # HTRIGHT
                    (False, False, True, False): 12,  # HTTOP
                    (False, False, False, True): 15,  # HTBOTTOM
                }.get((left, right, top, bottom))
                if hit:
                    return True, hit
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        # Сохраняем состояние всех виджетов
        try:
            if hasattr(self, "splitter") and isinstance(self.splitter, ResourceSplitter):
                if hasattr(self.splitter, "save_settings"):
                    self.splitter.save_settings()
        except Exception as e:
            logger.warning(f"save_settings(splitter): {e}")

        try:
            if (hasattr(self, "quota_widget") and self.quota_widget is not None
                    and hasattr(self.quota_widget, "save_settings")):
                self.quota_widget.save_settings()
        except Exception as e:
            logger.warning(f"save_settings(quota_widget): {e}")

        try:
            if hasattr(self, "timer_widget") and hasattr(self.timer_widget, "save_state"):
                self.timer_widget.save_state()
        except Exception as e:
            logger.warning(f"save_state(timer_widget): {e}")

        super().closeEvent(event)

    def quit_app(self):
        """Настоящий выход из приложения (в отличие от закрытия окна, которое сворачивает в трей)."""
        self._force_quit = True
        self.close()
        QtWidgets.QApplication.quit()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QtGui.QFont("Inter", 10)
    app.setFont(font)
    # Крестик закрывает приложение полностью (сворачивания в трей нет).
    app.setQuitOnLastWindowClosed(True)

    # Иконка приложения
    app_icon = QtGui.QIcon(resource_path("icon.ico"))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    else:
        logger.warning("Не удалось загрузить icon.ico")

    w = AppWindow()

    # Иконка в title_bar
    try:
        if hasattr(w, "title_bar") and getattr(w.title_bar, "icon_label", None) is not None:
            pix = QtGui.QPixmap(resource_path("icon.ico"))
            if not pix.isNull():
                pix = pix.scaled(28, 28, QtCore.Qt.KeepAspectRatio,
                                 QtCore.Qt.SmoothTransformation)
                w.title_bar.icon_label.setPixmap(pix)
    except Exception as e:
        logger.debug(f"Не удалось установить pixmap в title_bar: {e}")

    # Системный трей
    try:
        tray = QtWidgets.QSystemTrayIcon(app_icon, w)
        menu = QtWidgets.QMenu()
        show_action = menu.addAction(i18n.tr("tray_open", w.lang))
        quit_action = menu.addAction(i18n.tr("tray_quit", w.lang))

        def _restore_window():
            w.showNormal()
            w.raise_()
            w.activateWindow()

        show_action.triggered.connect(_restore_window)
        quit_action.triggered.connect(w.quit_app)

        def _on_tray_activated(reason):
            # Двойной клик по иконке — тоже разворачивает окно (обычный UX для трея)
            if reason == QtWidgets.QSystemTrayIcon.DoubleClick:
                _restore_window()

        tray.activated.connect(_on_tray_activated)
        tray.setContextMenu(menu)
        tray.setToolTip("Combined Foxhole Tools")
        tray.show()
        w._sys_tray_icon = tray
    except Exception as e:
        logger.warning(f"Не удалось создать системный трей: {e}")

    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
