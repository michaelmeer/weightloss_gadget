#!/usr/bin/python3

from tkinter import *
from tkinter import messagebox
from tkinter.ttk import *
from multiprocessing import Pipe, Process
from functools import partial

import configparser
import logging, logging.config
import time 
from PIL import Image, ImageTk

from gui_actions import GuiActions
import screens
import google_sheets_interface

class TkinterApp(object):
    def __init__(self, pipe):
        self.logger = logging.getLogger("TkinterApp")
        self.pipe = pipe

        self.top = Tk()
        self.top.title("Weightloss Tracker")
        screen_labelframe = LabelFrame(self.top, text = 'Screen')
        screen_labelframe.pack(fill = "both", expand = "yes", side = TOP)
        self.image_label = Label( screen_labelframe, relief = RAISED)
        self.image_label.pack(side = TOP)
        self.pipe = pipe

        leds_labelframe = LabelFrame(self.top, text = 'LEDs')
        leds_labelframe.pack(fill = "both", expand = "yes", side = TOP)
        led1 = Canvas(leds_labelframe, bg = "blue", height = 50, width = 50)
        led1.pack()
        action_labelframe = LabelFrame(self.top, text = 'Actions')
        action_labelframe.pack(fill = "both", expand = "yes", side = BOTTOM)
        b1_button = Button(action_labelframe, text = "B1", command = partial(self.button_callback, GuiActions.LEFT_BUTTON))
        b1_button.pack(side = LEFT, expand = True)
        left_button = Button(action_labelframe, text = "<", command = partial(self.button_callback, GuiActions.LEFT))
        left_button.pack(side = LEFT, expand = True)
        center_button = Button(action_labelframe, text = "*", command = partial(self.button_callback, GuiActions.ACTION))
        center_button.pack(side = LEFT, expand = True)
        right_button = Button(action_labelframe, text = ">", command = partial(self.button_callback, GuiActions.RIGHT))
        right_button.pack(side = LEFT, expand = True)
        b2_button = Button(action_labelframe, text = "B2", command = partial(self.button_callback, GuiActions.RIGHT_BUTTON))
        b2_button.pack(side = LEFT, expand = True)

        self.top.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.top.after(100, self.check_pipe_poll)

    def on_closing(self):
        self.pipe.send(GuiActions.EXIT_PROGRAM)
        self.top.destroy()

    def button_callback(self, action):
        self.pipe.send(action)

    def check_pipe_poll(self):
        self.logger.debug("check_pipe_poll")
        if self.pipe.poll():
            pil_image = self.pipe.recv()
            tk_image = ImageTk.PhotoImage(pil_image)
            self.image_label.configure(image=tk_image)
            self.image_label.image = tk_image

            self.image_label.pack(side=TOP)
        self.top.after(100, self.check_pipe_poll)

class Ssd1306App(Process):
    def __init__(self, pipe):
        ### DISPLAY PART ###
        super().__init__()    
        self.logger = logging.getLogger("Ssd1306App")
        self.pipe = pipe
        # Raspberry Pi pin configuration:
        self.RST = 24
        # Note the following are only used with SPI:
        self.DC = 23
        self.SPI_PORT = 0
        self.SPI_DEVICE = 0
        # 128x64 display with hardware SPI:
        self.disp = Adafruit_SSD1306.SSD1306_128_64(rst=self.RST, dc=self.DC, spi=SPI.SpiDev(self.SPI_PORT, self.SPI_DEVICE, max_speed_hz=8000000))

        # Initialize library.
        self.disp.begin()
        # Clear display.
        self.disp.clear()
        self.disp.display()

        self.update_frequency = 0.1
        
        ### ROTARY ENCODER INPUT ###
        GPIO.setwarnings(True)
        GPIO.setmode(GPIO.BCM)        

        self.Enc_A = 2             
        self.Enc_B = 4             
        self.Button = 3
        
        # Assume that rotary switch is not moving while we init software
        self.Current_A = 1           
        self.Current_B = 1

        
        # define the Encoder switch inputs
        GPIO.setup(self.Enc_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)             
        GPIO.setup(self.Enc_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # setup callback thread for the A and B encoder 
        # use interrupts for all inputs
        GPIO.add_event_detect(self.Enc_A, GPIO.RISING, callback=self.rotary_interrupt)
        GPIO.add_event_detect(self.Enc_B, GPIO.RISING, callback=self.rotary_interrupt)
        
        GPIO.setup(self.Button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.Button, GPIO.FALLING, callback=self.button_interrupt)
    
    def button_interrupt(self, button):
        self.logger.debug("Button pressed")
        self.pipe.send(GuiActions.ACTION)
        
    def rotary_interrupt(self, A_or_B):
        Switch_A = GPIO.input(self.Enc_A)
        Switch_B = GPIO.input(self.Enc_B)

        if self.Current_A == Switch_A and self.Current_B == Switch_B:
            return

        self.Current_A = Switch_A                        # remember new state
        self.Current_B = Switch_B                        # for next bouncing check

        if (Switch_A and Switch_B):
          if A_or_B == self.Enc_B:                     # Turning direction depends on 
            self.logger.debug("Rotary Encoder turns right")
            self.pipe.send(GuiActions.RIGHT )
          else:
            self.logger.debug("Rotary Encoder turns left")
            self.pipe.send(GuiActions.LEFT )
        
    def run(self):
        self.logger.debug("check_pipe_poll")

        while True:
            if self.pipe.poll():
                pil_image = self.pipe.recv()
                self.disp.image(pil_image)
                self.disp.display()
            time.sleep(self.update_frequency)
            
if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read(r"config.ini")

    logging.config.fileConfig(config, disable_existing_loggers=False)
    screens.logging.config.fileConfig(config, disable_existing_loggers=False)
    logger = logging.getLogger(__name__)
    logger.info("Loaded Logging Configuration")

    parent_conn, child_conn = Pipe()

    controller_process = screens.Controller(child_conn)

    frontend = config['WeightlossGadget']['frontend']
    if frontend == 'TkInter':
        tkinter_app = TkinterApp(parent_conn)
        controller_process.start()
        tkinter_app.top.mainloop()
        controller_process.join()
    elif frontend == 'Ssd1306':
        import Adafruit_GPIO.SPI as SPI
        import Adafruit_SSD1306
        import RPi.GPIO as GPIO

        ssd1306_app = Ssd1306App(parent_conn)
        ssd1306_app.start()
        controller_process.start()
        controller_process.join()
        ssd1306_app.join()
