
#Copyright (c) 2024 Seamus Byrne

#All rights reserved.

#This software was created by Seamus Byrne on March 15, 2024.

#Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "IV-Curve-Sweeper"), to deal in the IV-Curve-Sweeper without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the IV-Curve-Sweeper, and to permit persons to whom the IV-Curve-Sweeper is furnished to do so, subject to the following conditions:

#The above copyright notice and this permission notice shall be included in all copies or substantial portions of the IV-Curve-Sweeper.

#THE IV-CURVE-SWEEPER IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE IV-CURVE-SWEEPER OR THE USE OR OTHER DEALINGS IN THE IV-CURVE-SWEEPER.




import numpy as np
import time
import matplotlib.pyplot as plt
import csv
import threading
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pyvisa
import os
import sys

# Define global variables
stop_flag = False
Current2410 = []
Current617 = []
Current617A = []

def read_current_2410(keithley_2410):
    try:
        data = keithley_2410.query(":READ?").split(',')
        return float(data[1]) if len(data) > 1 else 0.0
    except pyvisa.errors.VisaIOError:
        return 0.0

def read_current(keithley, command='MEASURE?'):
    try:
        measurement = keithley.query(command).strip()
        numeric_value = ''.join(filter(lambda x: x.isdigit() or x in '.-E', measurement))
        return float(numeric_value) if numeric_value else 0.0
    except pyvisa.errors.VisaIOError:
        return 0.0

def zero_check_correct(keithley):
    commands = ['C1X', 'Z1X', 'Z0X', 'C0X', 'F1X']
    for cmd in commands:
        keithley.write(cmd)
        time.sleep(0.1)

def save_data_to_csv(voltage, current2410, current617, current617A, filename=''):
    # Ensure all arrays have the same length
    min_len = min(len(voltage), len(current2410), len(current617), len(current617A))
    
    # Use only the first `min_len` elements of each array
    voltage = voltage[:min_len]
    current2410 = current2410[:min_len]
    current617 = current617[:min_len]
    current617A = current617A[:min_len]

    data = np.column_stack([voltage, current2410, current617, current617A])

    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Voltage (V)', 'Current 2410', 'Current 617', 'Current 617A'])
        writer.writerows(data)

def ramp_down_voltage(keithley, current_voltage, step=-0.1, delay=0.1):
    while current_voltage != 0:
        if current_voltage < 0:
            step = abs(step)  # Ensure step is positive for negative voltages
        keithley.write(f":SOUR:VOLT {current_voltage}")
        time.sleep(delay)
        current_voltage += step
        if abs(current_voltage) < abs(step):
            current_voltage = 0
    keithley.write(":SOUR:VOLT 0")



def sweep(compliance, start_voltage, stop_voltage, step_size, ax, canvas, border):
    global stop_flag
    global Current2410
    global Current617
    global Current617A
    rm = pyvisa.ResourceManager()
    keithley_2410 = rm.open_resource('GPIB0::24::INSTR', timeout=10000)
    keithley_617A = rm.open_resource('GPIB0::8::INSTR')
    keithley_617 = rm.open_resource('GPIB0::10::INSTR')

    keithley_2410.write("*RST")
    keithley_2410.write(":ROUTe:TERMinals REAR")
    keithley_2410.write(":SOUR:FUNC:MODE VOLT")
    keithley_2410.write(f":SENS:CURR:PROT:LEV {compliance}")
    keithley_2410.write(":SENS:CURR:RANGE:AUTO 1")
    keithley_2410.write("OUTP ON")

    zero_check_correct(keithley_617A)
    zero_check_correct(keithley_617)

    Voltage = np.arange(start_voltage, stop_voltage + step_size, step_size)

    for V in Voltage:
        if stop_flag:  # Check stop flag
            print("Emergency stop button pressed. Ramping down voltage to zero...")
            ramp_down_voltage(keithley_2410, V, step=-0.1, delay=0.05)
            break

        keithley_2410.write(f":SOUR:VOLT {V}")
        time.sleep(0.001)

        currents2410, currents617, currents617A = [], [], []
        for _ in range(5):
            currents2410.append(read_current_2410(keithley_2410))
            currents617.append(read_current(keithley_617))
            currents617A.append(read_current(keithley_617A))

        Current2410.append(np.mean(currents2410))
        Current617.append(np.mean(currents617))
        Current617A.append(np.mean(currents617A))

        ax.clear()
        ax.plot(Voltage[:len(Current2410)], Current2410, "-o", label='2410 Current', color='blue')
        ax.plot(Voltage[:len(Current617)], Current617, "-x", label='617 Current', color='red')
        ax.plot(Voltage[:len(Current617A)], Current617A, "-*", label='617A Current', color='green')
        ax.set_xlim(min(start_voltage, stop_voltage), max(start_voltage, stop_voltage))
        ax.set_xlabel('Voltage (V)', color='darkred')
        ax.set_ylabel('Current (A)', color='darkred')
        ax.set_title('IV Curve', color='darkred')
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.5)
        ax.set_facecolor('#f0e0f0')  # Background color (very light purple)
        ax.legend()

        canvas.draw()

    final_voltage = Voltage[-1]
    ramp_down_step = -0.5 if final_voltage > 0 else 0.1
    ramp_down_voltage(keithley_2410, final_voltage, step=ramp_down_step, delay=0.05)
    
    # Set the green border
    canvas.get_tk_widget().config(highlightbackground="light green", highlightthickness=5)

    rm.close()

def start_sweep():
    global stop_flag
    stop_flag = False  # Reset stop flag
    try:
        compliance = float(compliance_entry.get())
        start_voltage = float(start_entry.get())
        stop_voltage = float(stop_entry.get())
        step_size = float(step_entry.get())

        if start_voltage < stop_voltage and step_size < 0:
            step_size = -step_size
        elif start_voltage > stop_voltage and step_size > 0:
            step_size = -step_size
    except ValueError:
        print("Invalid input. Please enter numeric values.")
        return

    fig, ax = plt.subplots()
    ax.set_xlabel('Voltage (V)', color='darkred')
    ax.set_ylabel('Current (A)', color='darkred')
    ax.set_title('IV Curve', color='darkred')
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.5)
    ax.set_facecolor('#f0e0f0')  # Background color (very light purple)

    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().grid(row=1, column=0, columnspan=3, pady=(20, 0), padx=(20, 20))

    # Start sweep thread
    sweep_thread = threading.Thread(target=sweep, args=(compliance, start_voltage, stop_voltage, step_size, ax, canvas, root))
    sweep_thread.start()

def stop_sweep():
    global stop_flag
    stop_flag = True  # Set stop flag to ensure that sweep thread stops immediately

    # Do immediate ramp down
    rm = pyvisa.ResourceManager()
    keithley_2410 = rm.open_resource('GPIB0::24::INSTR', timeout=10000)

    try:
        # Get the current voltage
        current_voltage = float(keithley_2410.query(":SOUR:VOLT?").strip())

        # Ramp down voltage immediately
        ramp_down_voltage(keithley_2410, current_voltage, step=-0.1, delay=0.05)
    except Exception as e:
        print("Exception during immediate ramp down:", e)
    finally:
        # Close resources
        keithley_2410.close()
        rm.close()

def save_data():
    global stop_flag
    stop_flag = True  # Stop the sweep

    filename = tk.filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if filename:
        try:
            start_voltage = float(start_entry.get())
            stop_voltage = float(stop_entry.get())
            step_size = float(step_entry.get())

            Voltage = np.arange(start_voltage, stop_voltage + step_size, step_size)
            # Retrieve the current data arrays
            Current2410_data = Current2410[:]
            Current617_data = Current617[:]
            Current617A_data = Current617A[:]
        except ValueError:
            print("Invalid input. Please enter numeric values for start voltage, stop voltage, and step size.")
            return

        # Save data to CSV file
        save_data_to_csv(Voltage, Current2410_data, Current617_data, Current617A_data, filename)

def reset_program():
    os.execv(sys.executable, ['python'] + sys.argv)

# GUI setup
root = tk.Tk()
root.title("IV Curve Sweeper - by Seamus Byrne")

# Labels and entry fields
compliance_label = tk.Label(root, text="Compliance (A):", fg='darkred')
compliance_label.grid(row=0, column=0)
compliance_entry = tk.Entry(root)
compliance_entry.grid(row=0, column=1)

start_label = tk.Label(root, text="Start Voltage (V):", fg='darkred')
start_label.grid(row=1, column=0)
start_entry = tk.Entry(root)
start_entry.grid(row=1, column=1)

stop_label = tk.Label(root, text="Stop Voltage (V):", fg='darkred')
stop_label.grid(row=2, column=0)
stop_entry = tk.Entry(root)
stop_entry.grid(row=2, column=1)

step_label = tk.Label(root, text="Step Size (V):", fg='darkred')
step_label.grid(row=3, column=0)
step_entry = tk.Entry(root)
step_entry.grid(row=3, column=1)

# Buttons
start_button = tk.Button(root, text="Start Sweep", command=start_sweep, bg="green", fg="white")
start_button.grid(row=4, column=0)

stop_button = tk.Button(root, text="Stop Sweep", command=stop_sweep, bg="red", fg="white")
stop_button.grid(row=4, column=1)

save_button = tk.Button(root, text="Save Data", command=save_data, bg="dark blue", fg="white")
save_button.grid(row=4, column=2)

reset_button = tk.Button(root, text="Reset", command=reset_program, bg="orange")
reset_button.grid(row=5, column=1)

# Set the green border
root.config(highlightbackground="light green", highlightthickness=5)

root.mainloop()
