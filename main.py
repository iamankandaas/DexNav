import cv2
import numpy as np
import pyautogui
import time
import tkinter as tk
import pyttsx3
import threading
import keyboard
import queue

pyautogui.PAUSE = 0

cap = cv2.VideoCapture(0)
screen_w, screen_h = pyautogui.size()

# Blue color range in HSV
lower_blue = np.array([100, 150, 50])
upper_blue = np.array([130, 255, 255])

position_history = []
scroll_mode = False
double_click_mode = False
last_scroll_y = None

LEFT_CLICK_HOLD_MIN = 1.0
RIGHT_CLICK_HOLD_MIN = 2.0

hold_start_time = None
click_type = None

SCROLL_THRESHOLD = 1
SCROLL_MULTIPLIER = 35

MARGIN_X = 80
MARGIN_Y = 60

# Voice engine setup
engine = pyttsx3.init()
engine.setProperty('rate', 125)
def speak(msg):
    engine.say(msg)
    engine.runAndWait()

# Queue for thread-safe GUI updates
message_queue = queue.Queue()

# -------- UI Overlay for Feedback -------- #
class FeedbackPopup:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry("240x60+50+50")
        self.label = tk.Label(self.root, text="", font=("Helvetica", 14), bg="black", fg="white")
        self.label.pack(fill=tk.BOTH, expand=True)
        self.root.withdraw()

    def show(self, msg, duration=1000):
        def _display():
            self.label.config(text=msg)
            self.root.deiconify()
            self.root.after(duration, self.root.withdraw)
        self.root.after(0, _display)

feedback = FeedbackPopup()

# -------- Idle Detection -------- #
class IdleManager:
    def __init__(self, timeout=10):
        self.timeout = timeout
        self.last_seen = time.time()
        self.idle = False

    def update(self, marker_detected):
        current = time.time()
        if marker_detected:
            if self.idle:
                self.idle = False
                message_queue.put(("Welcome Back!",))
            self.last_seen = current
        elif not self.idle and current - self.last_seen > self.timeout:
            self.idle = True
            message_queue.put(("Idle Mode",))

idle_manager = IdleManager(timeout=10)

# -------- Global Key Listening -------- #
def listen_for_keys():
    global scroll_mode, double_click_mode, last_scroll_y
    while True:
        if keyboard.is_pressed('s'):
            scroll_mode = not scroll_mode
            last_scroll_y = None
            msg = f"Scroll Mode: {'ON' if scroll_mode else 'OFF'}"
            message_queue.put((msg,))
            time.sleep(0.5)

        if keyboard.is_pressed('d'):
            double_click_mode = not double_click_mode
            msg = f"Double Click Mode: {'ON' if double_click_mode else 'OFF'}"
            message_queue.put((msg,))
            time.sleep(0.5)

listener_thread = threading.Thread(target=listen_for_keys, daemon=True)
listener_thread.start()

# -------- Main Loop -------- #
while True:
    feedback.root.update()

    # Handle queued messages from background thread
    while not message_queue.empty():
        msg_tuple = message_queue.get()
        if msg_tuple:
            msg = msg_tuple[0]
            feedback.show(msg)
            speak(msg)

    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    mask = cv2.GaussianBlur(mask, (7, 7), 0)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    marker_found = False

    if contours:
        max_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(max_contour) > 500:
            M = cv2.moments(max_contour)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                marker_found = True

                cv2.circle(frame, (cx, cy), 10, (255, 0, 0), -1)

                if scroll_mode:
                    if last_scroll_y is not None:
                        dy = cy - last_scroll_y
                        if abs(dy) > SCROLL_THRESHOLD:
                            scroll_direction = -1 if dy > 0 else 1
                            pyautogui.scroll(scroll_direction * SCROLL_MULTIPLIER)
                    last_scroll_y = cy
                else:
                    screen_x = np.interp(cx, [-MARGIN_X, frame.shape[1] + MARGIN_X], [0, screen_w])
                    screen_y = np.interp(cy, [-MARGIN_Y, frame.shape[0] + MARGIN_Y], [0, screen_h])
                    pyautogui.moveTo(screen_x, screen_y)

                    position_history.append((cx, cy))
                    if len(position_history) > 20:
                        position_history.pop(0)

                    if len(position_history) == 20:
                        x_vals = [p[0] for p in position_history]
                        y_vals = [p[1] for p in position_history]
                        if (max(x_vals) - min(x_vals) < 25) and (max(y_vals) - min(y_vals) < 25):
                            if hold_start_time is None:
                                hold_start_time = time.time()
                                click_type = None
                            else:
                                duration = time.time() - hold_start_time
                                if double_click_mode and duration >= LEFT_CLICK_HOLD_MIN and click_type != "double":
                                    pyautogui.doubleClick()
                                    feedback.show("Double Click!")
                                    speak("Double click")
                                    click_type = "double"
                                elif not double_click_mode:
                                    if duration >= RIGHT_CLICK_HOLD_MIN and click_type != "right":
                                        pyautogui.rightClick()
                                        feedback.show("Right Click!")
                                        speak("Right click")
                                        click_type = "right"
                        else:
                            if hold_start_time:
                                duration = time.time() - hold_start_time
                                if LEFT_CLICK_HOLD_MIN <= duration < RIGHT_CLICK_HOLD_MIN and not double_click_mode:
                                    pyautogui.click()
                                    feedback.show("Left Click!")
                                    speak("Left click")
                            hold_start_time = None
                            click_type = None
    else:
        if hold_start_time and click_type is None and not double_click_mode:
            duration = time.time() - hold_start_time
            if LEFT_CLICK_HOLD_MIN <= duration < RIGHT_CLICK_HOLD_MIN:
                pyautogui.click()
                feedback.show("Left Click!")
                speak("Left click")
        hold_start_time = None
        click_type = None

    idle_manager.update(marker_found)

    mode_text = "SCROLL" if scroll_mode else "MOUSE"
    extra = " + DOUBLE" if double_click_mode else ""
    cv2.putText(frame, f"DexNav: {mode_text} MODE{extra}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)

    cv2.imshow("DexNav - Color Marker", frame)
    cv2.imshow("DexNav - Mask", mask)
    cv2.moveWindow("DexNav - Color Marker", 100, 100)
    cv2.moveWindow("DexNav - Mask", 750, 100)

    if cv2.waitKey(1) == 27:
        break

cap.release()
cv2.destroyAllWindows()
