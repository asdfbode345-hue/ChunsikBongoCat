"""Chunsik BongoCat v2 - independent paws and per-key tracking on Windows."""
import sys, time, math
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QObject, Signal, QRectF, QPoint
from PySide6.QtGui import QPainter, QPixmap, QAction, QIcon, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon
from pynput import keyboard, mouse

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ASSETS = ROOT / 'assets'
W, H = 1672, 941
# Source image pixel coordinates. The right paw switches between mouse and keyboard.
HOME = {'left': (488., 650.), 'right': (1099., 678.)}
# Keyboard illustration covers approximately x=210..930, y=690..835.
ROWS = [('1234567890-=', 247, 714, 57), ('qwertyuiop[]\\', 273, 748, 53),
        ('asdfghjkl;\'', 294, 782, 55), ('zxcvbnm,./', 343, 810, 56)]
KEYS = {}
for chars, start, y, step in ROWS:
    for i, ch in enumerate(chars):
        KEYS[ch] = (start + i * step, y)
KEYS.update({' ': (575, 823), 'space': (575, 823), 'enter': (869, 786),
             'backspace': (880, 715), 'tab': (240, 748), 'shift': (315, 810),
             'shift_l': (315, 810), 'shift_r': (850, 810), 'ctrl_l': (246, 824),
             'ctrl_r': (840, 824), 'alt_l': (425, 824), 'alt_r': (760, 824),
             'esc': (238, 705), 'up': (808, 804), 'down': (808, 828),
             'left': (770, 828), 'right': (846, 828)})

class Signals(QObject):
    key = Signal(str)
    mouse_move = Signal(float, float)
    mouse_click = Signal(str, bool)

class Overlay(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.base = QPixmap(str(ASSETS/'base.png'))
        self.paws = {s: QPixmap(str(ASSETS/f'paw_{s}.png')) for s in HOME}
        self.original = QPixmap(str(ASSETS/'original.png'))
        if any(p.isNull() for p in [self.base, self.original, *self.paws.values()]):
            raise RuntimeError('캐릭터 이미지 파일이 없습니다.')
        self.signals = Signals()
        self.signals.key.connect(self.on_key)
        self.signals.mouse_move.connect(self.on_mouse_move)
        self.signals.mouse_click.connect(self.on_mouse_click)
        self.targets = dict(HOME)
        self.positions = dict(HOME)
        self.key_deadlines = {'left': 0., 'right': 0.}
        self.last_key_side = 'right'
        self.mouse_xy = (0., 0.)
        self.mouse_active_until = 0.
        self.click_until = 0.
        self.frame = 0
        self.always_on_top = True
        self.drag_offset = None
        self.width_setting = 420
        self.setWindowTitle('춘식이 봉고캣 v2')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self.window_flags())
        self.setFixedSize(self.width_setting, round(self.width_setting*H/W))
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right()-self.width()-25, screen.bottom()-self.height()-30)
        self.make_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.kb = keyboard.Listener(on_press=self.keyboard_callback)
        self.ms = mouse.Listener(on_move=lambda x,y:self.signals.mouse_move.emit(float(x),float(y)),
                                 on_click=lambda x,y,button,pressed:self.signals.mouse_click.emit(str(button),pressed))
        self.kb.start()
        self.ms.start()
        self.show()

    def window_flags(self):
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        return f | (Qt.WindowType.WindowStaysOnTopHint if self.always_on_top else Qt.WindowType(0))

    def keyboard_callback(self, key):
        try:
            name = key.char.lower() if key.char else ''
        except AttributeError:
            name = ''
        if not name:
            name = str(key).replace('Key.', '').lower()
        self.signals.key.emit(name)

    def on_key(self, name):
        if name not in KEYS:
            name = 'space' if name in ('space', 'spacebar') else 'enter'
        x, y = KEYS[name]
        # Keyboard split follows the key position, not random alternating paws.
        side = 'left' if x < 585 else 'right'
        now = time.monotonic()
        self.targets[side] = (x, y-54)
        self.key_deadlines[side] = now + .18
        self.last_key_side = side

    def on_mouse_move(self, x, y):
        self.mouse_xy = (x, y)
        self.mouse_active_until = time.monotonic() + .35

    def on_mouse_click(self, button, pressed):
        if pressed:
            self.click_until = time.monotonic() + .15
            self.mouse_active_until = time.monotonic() + .55

    def tick(self):
        now = time.monotonic()
        self.frame += 1
        if now < self.mouse_active_until and now >= self.key_deadlines['right']:
            geo = QApplication.primaryScreen().geometry()
            mx, my = self.mouse_xy
            nx = max(0., min(1., (mx-geo.left())/max(1,geo.width())))
            ny = max(0., min(1., (my-geo.top())/max(1,geo.height())))
            self.targets['right'] = (1070 + nx*115, 675 + ny*65 + (12 if now < self.click_until else 0))
        for side in HOME:
            if now > self.key_deadlines[side] and (side == 'left' or now > self.mouse_active_until):
                self.targets[side] = HOME[side]
            x,y = self.positions[side]
            tx,ty = self.targets[side]
            self.positions[side] = (x+(tx-x)*.31, y+(ty-y)*.31)
        if self.isVisible(): self.update()

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(self.width()/W, self.height()/H)
        p.drawPixmap(0,0,self.base)
        # keyboard hit highlight at the exact illustrated key coordinate
        now=time.monotonic()
        for side in HOME:
            if now < self.key_deadlines[side]:
                tx,ty=self.targets[side]
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255,178,204,85))
                p.drawEllipse(QRectF(tx-23,ty+37,46,24))
        for side in ('left','right'):
            x,y=self.positions[side]
            paw=self.paws[side]
            p.drawPixmap(QRectF(x-paw.width()/2,y-paw.height()/2,paw.width(),paw.height()),paw,QRectF(paw.rect()))
        p.end()

    def make_tray(self):
        self.tray=QSystemTrayIcon(QIcon(self.original),self)
        self.menu=QMenu()
        self.show_action=QAction('춘식이 숨기기',self)
        self.show_action.triggered.connect(self.toggle_visible)
        self.menu.addAction(self.show_action)
        self.top_action=QAction('항상 위에 표시',self,checkable=True)
        self.top_action.setChecked(True)
        self.top_action.triggered.connect(self.toggle_top)
        self.menu.addAction(self.top_action)
        self.menu.addSeparator()
        for label,w in [('작게 (300px)',300),('보통 (420px)',420),('크게 (600px)',600)]:
            a=QAction(label,self)
            a.triggered.connect(lambda checked=False,width=w:self.change_size(width))
            self.menu.addAction(a)
        self.menu.addSeparator()
        exit_action=QAction('종료',self)
        exit_action.triggered.connect(self.quit_app)
        self.menu.addAction(exit_action)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason:self.toggle_visible() if reason==QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.setToolTip('춘식이 봉고캣 v2')
        self.tray.show()

    def toggle_visible(self):
        if self.isVisible():
            self.hide();self.show_action.setText('춘식이 보이기')
        else:
            self.show();self.show_action.setText('춘식이 숨기기')

    def toggle_top(self, checked):
        visible=self.isVisible()
        self.always_on_top=checked
        self.setWindowFlags(self.window_flags())
        if visible:self.show()

    def change_size(self,width):
        self.width_setting=width
        self.setFixedSize(width,round(width*H/W))

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.drag_offset=event.globalPosition().toPoint()-self.frameGeometry().topLeft()

    def mouseMoveEvent(self,event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self,event):
        self.drag_offset=None

    def contextMenuEvent(self,event):
        self.menu.exec(event.globalPos())

    def quit_app(self):
        self.kb.stop();self.ms.stop();self.tray.hide();self.app.quit()

if __name__=='__main__':
    app=QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window=Overlay(app)
    sys.exit(app.exec())
