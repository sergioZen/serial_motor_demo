#!/usr/bin/env python3
import rospy
import numpy as np
from serial_motor_demo_msgs.msg import MotorCommand
from serial_motor_demo_msgs.msg import MotorVels
from serial_motor_demo_msgs.msg import EncoderVals
import time
import math
import serial
from threading import Lock
from serial.serialutil import SerialException

class MotorDriver():

    def __init__(self):
        # Setup parameters
        self.encoder_cpr = rospy.get_param("~encoder_cpr", 0)
        self.loop_rate = int(rospy.get_param("~loop_rate", 0))
        self.serial_port = rospy.get_param("~serial_port", "/dev/ttyUSB0")
        self.baud_rate = rospy.get_param("~baud_rate", 57600)
        self.debug_serial_cmds = rospy.get_param("~serial_debug", False)

        # Overall loop rate: should be faster than fastest sensor rate
        self.rate = int(rospy.get_param("~rate", 50))
        rospy.Rate(self.rate)

        # Setup topics & services
        
        rospy.Subscriber("motor_command", MotorCommand, self.motor_command_callback)

        # A cmd_vel publisher so we can stop the robot when shutting down
        self.speed_pub = rospy.Publisher('motor_vels', MotorVels, queue_size=10)
        self.encoder_pub = rospy.Publisher('encoder_vals', EncoderVals, queue_size=10)

        # Member Variables

        self.last_enc_read_time = time.time()
        self.last_m1_enc = 0
        self.last_m2_enc = 0
        self.m1_spd = 0.0
        self.m2_spd = 0.0

        self.mutex = Lock()

        # Open serial comms

        print(f"Connecting to port {self.serial_port} at {self.baud_rate}.")
        self.conn = serial.Serial(self.serial_port, self.baud_rate, timeout=1.0)
        print(f"Connected to {self.conn}")

    # Raw serial commands
    
    def send_pwm_motor_command(self, mot_1_pwm, mot_2_pwm):
        self.send_command(f"o {int(mot_1_pwm)} {int(mot_2_pwm)}")

    def send_feedback_motor_command(self, mot_1_ct_per_loop, mot_2_ct_per_loop):
        self.send_command(f"m {int(mot_1_ct_per_loop)} {int(mot_2_ct_per_loop)}")

    def send_encoder_read_command(self):
        resp = self.send_command(f"e")
        if resp:
            return [int(raw_enc) for raw_enc in resp.split()]
        return []


    # More user-friendly functions

    def motor_command_callback(self, motor_command):
        if (motor_command.is_pwm):
            self.send_pwm_motor_command(motor_command.mot_1_req_rad_sec, motor_command.mot_2_req_rad_sec)
        else:
            # counts per loop = req rads/sec X revs/rad X counts/rev X secs/loop 
            # SBR:  scaler = (1 / (2*math.pi)) * self.encoder_cpr * (1 / self.encoder_cpr)
           # scaler = encoder counts per radian 
            scaler = self.encoder_cpr / (2*math.pi)
            mot1_ct_per_loop = motor_command.mot_1_req_rad_sec * scaler
            mot2_ct_per_loop = motor_command.mot_2_req_rad_sec * scaler
            self.send_feedback_motor_command(mot1_ct_per_loop, mot2_ct_per_loop)

    def check_encoders(self):
        resp = self.send_encoder_read_command()
        if (resp):

            new_time = time.time()
            time_diff = new_time - self.last_enc_read_time
            self.last_enc_read_time = new_time

            m1_diff = resp[0] - self.last_m1_enc
            self.last_m1_enc = resp[0]
            m2_diff = resp[1] - self.last_m2_enc
            self.last_m2_enc = resp[1]

            rads_per_ct = 2*math.pi/self.encoder_cpr
            self.m1_spd = m1_diff*rads_per_ct/time_diff
            self.m2_spd = m2_diff*rads_per_ct/time_diff

            spd_msg = MotorVels()
            spd_msg.mot_1_rad_sec = self.m1_spd
            spd_msg.mot_2_rad_sec = self.m2_spd
            self.speed_pub.publish(spd_msg)

            enc_msg = EncoderVals()
            enc_msg.mot_1_enc_val = self.last_m1_enc
            enc_msg.mot_2_enc_val = self.last_m2_enc
            self.encoder_pub.publish(enc_msg)



    # Utility functions

    def send_command(self, cmd_string):
        
        self.mutex.acquire()
        try:
            cmd_string += "\r"
            self.conn.write(cmd_string.encode("utf-8"))
            if (self.debug_serial_cmds):
                print("Sent: " + cmd_string)

            ## Adapted from original
            c = ''
            value = ''
            while c != '\r':
                c = self.conn.read(1).decode("utf-8")
                if (c == ''):
                    print("Error: Serial timeout on command: " + cmd_string)
                    return ''
                value += c

            value = value.strip('\r')

            if (self.debug_serial_cmds):
                print("Received: " + value)
            return value
        finally:
            self.mutex.release()

    def close_conn(self):
        self.conn.close()


if __name__ == '__main__':
    
    rospy.init_node('serial_motor_demo', log_level=rospy.INFO)

    # Get the actual node name in case it is set in the launch file
    nodename = rospy.get_name()

    motor_driver = MotorDriver()

    idle = rospy.Rate(10)
    then = rospy.Time.now()
    
    ###### main loop  ######
    while not rospy.is_shutdown():
      motor_driver.check_encoders()
      
      # rospy.spin()

      idle.sleep()    

    motor_driver.close_conn()
    motor_driver.destroy_node()
    rospy.shutdown()
