"""Chunsik BongoCat v3 - rapid tap animation and per-key tracking on Windows."""
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
    key = Signal(str, bool)
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
        self.anim = {side: None for side in HOME}
        self.last_press = {}
        self.pressed_keys = set()
        self.tap_duration = .115
        self.tap_lift = 31
        self.last_tick = time.monotonic()
        self.mouse_xy = (0., 0.)
        self.mouse_active_until = 0.
        self.click_until = 0.
        self.frame = 0
        self.always_on_top = True
        self.drag_offset = None
        self.width_setting = 420
        self.setWindowTitle('신춘식 봉고캣 v3')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(self.window_flags())
        self.setFixedSize(self.width_setting, round(self.width_setting*H/W))
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right()-self.width()-25, screen.bottom()-self.height()-30)
        self.make_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.kb = keyboard.Listener(on_press=lambda key:self.keyboard_callback(key, True),
                                    on_release=lambda key:self.keyboard_callback(key, False))
        self.ms = mouse.Listener(on_move=lambda x,y:self.signals.mouse_move.emit(float(x),float(y)),
                                 on_click=lambda x,y,button,pressed:self.signals.mouse_click.emit(str(button),pressed))
        self.kb.start()
        self.ms.start()
        self.show()

    def window_flags(self):
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        return f | (Qt.WindowType.WindowStaysOnTopHint if self.always_on_top else Qt.WindowType(0))

    def keyboard_callback(self, key, pressed):
        try:
            name = key.char.lower() if key.char else ''
        except AttributeError:
            name = ''
        if not name:
            name = str(key).replace('Key.', '').lower()
        self.signals.key.emit(name, pressed)

    def on_key(self, name, pressed):
        if name not in KEYS:
            return  # Unknown keys should not make the paws jump to Enter.
        now = time.monotonic()
        if not pressed:
            self.pressed_keys.discard(name)
            return
        # Windows auto-repeat can fire dozens of duplicate presses while held.
        if name in self.pressed_keys and now-self.last_press.get(name, 0) < .10:
            return
        self.pressed_keys.add(name)
        self.last_press[name] = now
        x, y = KEYS[name]
        side = 'left' if x < 585 else 'right'
        self.anim[side] = {'start':now, 'from':self.positions[side],
                           'to':(float(x), float(y-48)), 'key':name}
        self.key_deadlines[side] = now + self.tap_duration
        self.last_key_side = side

    def on_mouse_move(self, x, y):
        self.mouse_xy = (x, y)
        self.mouse_active_until = time.monotonic() + .35

    def on_mouse_click(self, button, pressed):
        if pressed:
            self.click_until = time.monotonic() + .15
            self.mouse_active_until = time.monotonic() + .55

    @staticmethod
    def smooth(t):
        t=max(0., min(1.,t))
        return t*t*(3-2*t)

    def tick(self):
        now = time.monotonic()
        dt = min(.05, max(.001, now-self.last_tick))
        self.last_tick = now
        self.frame += 1
        for side in HOME:
            a = self.anim[side]
            if a is not None:
                t = (now-a['start'])/self.tap_duration
                if t >= 1.:
                    self.anim[side] = None
                else:
                    # Fast, distinct lift -> strike -> recoil. No long floaty glide.
                    if t < .34:
                        k=self.smooth(t/.34)
                        x=a['from'][0]+(a['to'][0]-a['from'][0])*k
                        y=a['from'][1]+(a['to'][1]-a['from'][1])*k-self.tap_lift*math.sin(math.pi*k/2)
                    elif t < .61:
                        k=self.smooth((t-.34)/.27)
                        x=a['to'][0]
                        y=a['to'][1]-self.tap_lift*(1-k)+9*math.sin(math.pi*k)
                    else:
                        k=self.smooth((t-.61)/.39)
                        x=a['to'][0]+(HOME[side][0]-a['to'][0])*k
                        y=a['to'][1]+(HOME[side][1]-a['to'][1])*k-12*math.sin(math.pi*k)
                    self.positions[side]=(x,y)
                    continue
            if side=='right' and now < self.mouse_active_until:
                geo=QApplication.primaryScreen().geometry()
                mx,my=self.mouse_xy
                nx=max(0.,min(1.,(mx-geo.left())/max(1,geo.width())))
                ny=max(0.,min(1.,(my-geo.top())/max(1,geo.height())))
                target=(1070+nx*115, 675+ny*65+(9 if now<self.click_until else 0))
            else:
                target=HOME[side]
            # Frame-rate independent damping: responsive mouse, gentle return.
            k=1-math.exp(-dt*(27 if side=='right' and now<self.mouse_active_until else 19))
            x,y=self.positions[side]
            self.positions[side]=(x+(target[0]-x)*k,y+(target[1]-y)*k)
        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(self.width()/W, self.height()/H)
        p.drawPixmap(0,0,self.base)
        # keyboard hit highlight at the exact illustrated key coordinate
        now=time.monotonic()
        for side in HOME:
            if self.anim[side] is not None and .34 < (now-self.anim[side]['start'])/self.tap_duration < .75:
                tx,ty=self.anim[side]['to']
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
        self.tray.setToolTip('신춘식 봉고캣 v3')
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
