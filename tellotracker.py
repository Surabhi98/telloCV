"""
tellotracker:
Allows manual operation of the drone and demo tracking mode.

Requires mplayer to record/save video.

Controls:
- tab to lift off
- WASD to move the drone
- space/shift to ascend/descent slowly
- Q/E to yaw slowly
- arrow keys to ascend, descend, or yaw quickly
- backspace to land, or P to palm-land
- enter to take a picture
- R to start recording video, R again to stop recording
  (video and photos will be saved to a timestamped file in ~/Pictures/)
- Z to toggle camera zoom state
  (zoomed-in widescreen or high FOV 4:3)
- T to toggle tracking
@author Leonie Buckley, Saksham Sinha and Jonathan Byrne
@copyright 2018 see license file for details
"""

import time
import sys
import imutils
import numpy
import tellopy
import os
import datetime
import av
import cv2

from pynput import keyboard
from tracker import Tracker
from subprocess import Popen, PIPE


def main():

    tellotrack = TelloTracker()

    # container for processing the packets into frames
    container = av.open(tellotrack.drone.get_video_stream())
    video_st = container.streams.video[0]

    for packet in container.demux((video_st,)):
        for frame in packet.decode():

            # convert frame to cv2 image and show
            image = cv2.cvtColor(numpy.array(
                frame.to_image()), cv2.COLOR_RGB2BGR)
            tellotrack.write_hud(image)
            cv2.imshow('frame', image)
            key = cv2.waitKey(1) & 0xFF
            # tellotrack.key_press()
            # for e in pygame.event.get():
            #     tellotrack.key_event(e)



class TelloTracker(object):

    def __init__(self):
        self.prev_flight_data = None
        self.video_player = None
        self.video_recorder = None
        self.tracking = False
        self.font = None
        self.wid = None
        self.date_fmt = '%Y-%m-%d_%H%M%S'
        self.speed = 30
        self.drone = tellopy.Tello()
        self.init_drone()
        self.init_controls()

    def init_drone(self):
        print("connecting to drone")
        # self.drone.log.set_level(2)
        self.drone.connect()
        self.drone.start_video()
        self.drone.subscribe(self.drone.EVENT_FLIGHT_DATA,
                             self.flightDataHandler)
        #self.drone.subscribe(self.drone.EVENT_VIDEO_FRAME, self.videoFrameHandler)
        self.drone.subscribe(self.drone.EVENT_FILE_RECEIVED,
                             self.handleFileReceived)

    def on_press(self,keyname):
        try:
            keyname = str(keyname).strip('\'')
            print('+' + keyname)
            if keyname == 'Key.esc':
                self.drone.quit()
                exit(0)
            if keyname in self.controls:
                key_handler = self.controls[keyname]
                if type(key_handler) == str:
                    getattr(self.drone, key_handler)(self.speed)
                else:
                    key_handler(self, self.speed)
        except AttributeError:
            print('special key {0} pressed'.format(keyname))

    def on_release(self, keyname):
        keyname = str(keyname).strip('\'')
        print('-' + keyname)
        if keyname in self.controls:
            key_handler = self.controls[keyname]
            if type(key_handler) == str:
                getattr(self.drone, key_handler)(0)
            else:
                key_handler(self.drone, 0)


    def init_controls(self):
        self.controls = {
            'w': 'forward',
            's': 'backward',
            'a': 'left',
            'd': 'right',
            'Key.space': 'up',
            'Key.shift': 'down',
            'Key.shift_r': 'down',
            'q': 'counter_clockwise',
            'e': 'clockwise',
            'i': lambda drone, speed: self.drone.flip_forward(),
            'k': lambda drone, speed: self.drone.flip_back(),
            'j': lambda drone, speed: self.drone.flip_left(),
            'l': lambda drone, speed: self.drone.flip_right(),            
            # arrow keys for fast turns and altitude adjustments
            'Key.left': lambda drone, speed: self.drone.counter_clockwise(speed * 2),
            'Key.right': lambda drone, speed: self.drone.clockwise(speed * 2),
            'Key.up': lambda drone, speed: self.drone.up(speed * 2),
            'Key.down': lambda drone, speed: self.drone.down(speed * 2),
            'Key.tab': lambda drone, speed: self.drone.takeoff(),
            'Key.backspace': lambda drone, speed: self.drone.land(),
            'p': lambda drone, speed: self.palm_land(speed),
            't': lambda drone, speed: self.toggle_tracking(speed),
            'r': lambda drone, speed: self.toggle_recording(speed),
            'z': lambda drone, speed: self.toggle_zoom(speed),
            'Key.enter': lambda drone, speed: self.take_picture(speeds),
        }
        print("starting key listener")
        self.key_listener = keyboard.Listener(on_press=self.on_press,
                                              on_release=self.on_release)
        self.key_listener.start()
        # self.key_listener.join()

    def write_hud(self, frame):
        #cv2.putText(frame, "Height:", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 0), lineType=cv2.LINE_AA)
        stats = self.prev_flight_data.split('|')
        stats.append("Tracking:" + str(self.tracking))
        for idx, stat in enumerate(stats):
            text = stat.lstrip()
            cv2.putText(frame, text, (0, idx * 30), cv2.FONT_HERSHEY_SIMPLEX,
                        1.0, (255, 0, 0), lineType=cv2.LINE_AA)

    def toggle_recording(self, speed):
        if speed == 0:
            return

        if self.video_recorder:
            # already recording, so stop
            self.video_recorder.stdin.close()
            status_print('Video saved to %s' %
                         self.video_recorder.video_filename)
            self.video_recorder = None
            return

        # start a new recording
        filename = '%s/Pictures/tello-%s.mp4' % (os.getenv('HOME'),
                                                 datetime.datetime.now().strftime(self.date_fmt))

        cmd = ['mencoder', '-', '-vc', 'x264', '-fps', '30', '-ovc', 'copy', '-of', 'lavf',
               '-lavfopts', 'format=mp4', '-o', filename]
        self.video_recorder = Popen(cmd, stdin=PIPE)
        self.video_recorder.video_filename = filename
        status_print('Recording video to %s' % filename)

    def take_picture(self, speed):
        if speed == 0:
            return
        self.drone.take_picture()

    def palm_land(self, speed):
        if speed == 0:
            return
        self.drone.palm_land()

    def toggle_tracking(self, speed):
        if speed == 0:  # handle key up event
            return
        self.tracking = not(self.tracking)
        print("tracking:", self.tracking)
        return

    def toggle_zoom(self, speed):
        # In "video" mode the self.drone sends 1280x720 frames.
        # In "photo" mode it sends 2592x1936 (952x720) frames.
        # The video will always be centered in the window.
        # In photo mode, if we keep the window at 1280x720 that gives us ~160px on
        # each side for status information, which is ample.
        # Video mode is harder because then we need to abandon the 16:9 display size
        # if we want to put the HUD next to the video.
        if speed == 0:
            return
        self.drone.set_video_mode(not self.drone.zoom)

    def flight_data_mode(self, *args):
        return (self.drone.zoom and "VID" or "PIC")

    def flight_data_recording(self, *args):
        # TODO: duration of recording
        return (self.video_recorder and "REC 00:00" or "")

    def flightDataHandler(self, event, sender, data):
        text = str(data)
        if self.prev_flight_data != text:
            self.prev_flight_data = text
        #self.update_hud(sender, data)

    def handleFileReceived(event, sender, data):
        global date_fmt
        # Create a file in ~/Pictures/ to receive image data from the
        # self.drone.
        path = '%s/Pictures/tello-%s.jpeg' % (
            os.getenv('HOME'),
            datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S'))
        with open(path, 'wb') as fd:
            fd.write(data)
        status_print('Saved photo to %s' % path)

if __name__ == '__main__':
    main()
