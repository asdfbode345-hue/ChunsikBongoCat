"""Chunsik BongoCat v1.0 - Windows desktop overlay."""
import sys
import math
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, Signal, QObject
from PySide6.QtGui import QPixmap, QPainter, QIcon, QAction, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from pynput import keyboard, mouse

ROOT = Path(__file__).resolve().parent
IMAGE = ROOT / 'assets' / 'chunsik.png'

class Events(QObject):
    typing = Signal()
    clicking = Signal()
    moving = Signal()

class Overlay(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.events = Events()
        self.events.typing.connect(self.on_type)
        self.events.clicking.connect(self.on_click)
        self.events.moving.connect(self.on_move)
        self.image = QPixmap(str(IMAGE))
        if self.image.isNull():
            raise RuntimeError('assets/chunsik.png 이미지가 없습니다.')
        self.scale_width = 400
        self.always_on_top = True
        self.frame = 0
        self.key_ttl = 0
        self.click_ttl = 0
        self.move_ttl = 0
        self.drag_start = None
        self.setWindowTitle('춘식이 봉고캣')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self.flags())
        self.resize(self.scale_width, round(self.scale_width * self.image.height() / self.image.width()))
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 28, screen.bottom() - self.height() - 28)
        self.make_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        self.kb_listener = keyboard.Listener(on_press=lambda key: self.events.typing.emit())
        self.ms_listener = mouse.Listener(on_click=lambda *args: self.events.clicking.emit() if args[3] else None,
                                          on_move=lambda *args: self.events.moving.emit())
        self.kb_listener.start()
        self.ms_listener.start()
        self.show()

    def flags(self):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        return flags

    def make_tray(self):
        self.tray = QSystemTrayIcon(QIcon(self.image), self)
        self.menu = QMenu()
        self.visible_action = QAction('춘식이 숨기기', self)
        self.visible_action.triggered.connect(self.toggle_visible)
        self.menu.addAction(self.visible_action)
        self.top_action = QAction('항상 위에 표시', self)
        self.top_action.setCheckable(True)
        self.top_action.setChecked(True)
        self.top_action.triggered.connect(self.toggle_top)
        self.menu.addAction(self.top_action)
        self.menu.addSeparator()
        for label, width in [('작게 (280px)', 280), ('보통 (400px)', 400), ('크게 (560px)', 560)]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, w=width: self.change_size(w))
            self.menu.addAction(action)
        self.menu.addSeparator()
        quit_action = QAction('프로그램 종료', self)
        quit_action.triggered.connect(self.quit_app)
        self.menu.addAction(quit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_clicked)
        self.tray.setToolTip('춘식이 봉고캣: 우클릭하여 설정')
        self.tray.show()

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
            self.visible_action.setText('춘식이 보이기')
        else:
            self.show()
            self.visible_action.setText('춘식이 숨기기')

    def toggle_top(self, checked):
        was_visible = self.isVisible()
        self.always_on_top = checked
        self.setWindowFlags(self.flags())
        if was_visible:
            self.show()

    def change_size(self, width):
        self.scale_width = width
        self.resize(width, round(width * self.image.height() / self.image.width()))
        self.update()

    def on_type(self):
        self.key_ttl = 9

    def on_click(self):
        self.click_ttl = 11

    def on_move(self):
        self.move_ttl = 6

    def tick(self):
        self.frame += 1
        self.key_ttl = max(0, self.key_ttl - 1)
        self.click_ttl = max(0, self.click_ttl - 1)
        self.move_ttl = max(0, self.move_ttl - 1)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        sx = self.width() / self.image.width()
        sy = self.height() / self.image.height()
        # The first prototype uses a subtle bounce and input highlights.
        bob = math.sin(self.frame * .075) * 1.2
        if self.key_ttl:
            bob -= 3.5 if self.frame % 4 < 2 else 0
        if self.click_ttl:
            bob -= 2
        painter.drawPixmap(QRectF(0, bob + 3, self.width(), self.height() - 4), self.image, QRectF(self.image.rect()))
        painter.setPen(Qt.PenStyle.NoPen)
        if self.key_ttl:
            opacity = min(0.7, self.key_ttl / 12)
            painter.setBrush(QColor(255, 230, 110, int(135 * opacity)))
            for x, y in [(380, 750), (560, 785), (800, 790)]:
                painter.drawEllipse(QRectF(x*sx-9, y*sy-7, 18, 14))
        if self.click_ttl:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 116, 166, int(220*self.click_ttl/11)), 3))
            cx, cy = 1195*sx, 780*sy
            r = (15 + (11-self.click_ttl)*2) * sx
            painter.drawEllipse(QPoint(round(cx), round(cy)), round(r), round(r*.6))
        if self.move_ttl:
            painter.setBrush(QColor(255, 180, 205, int(100*self.move_ttl/6)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(1150*sx, 720*sy, 35*sx, 18*sy))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_start = None

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def quit_app(self):
        self.kb_listener.stop()
        self.ms_listener.stop()
        self.tray.hide()
        self.app.quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = Overlay(app)
    sys.exit(app.exec())
