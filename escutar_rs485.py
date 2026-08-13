import serial
import time

PORTA = "COM8"
BAUDRATE = 9600
PARIDADE = "N"
STOPBITS = 2

ser = serial.Serial(
    port=PORTA,
    baudrate=BAUDRATE,
    bytesize=8,
    parity=PARIDADE,
    stopbits=STOPBITS,
    timeout=0.2,
)

print("=" * 60)
print("MONITOR RS485 - SOMENTE ESCUTA")
print(f"{PORTA} | {BAUDRATE} | 8{PARIDADE}{STOPBITS}")
print("Nenhum dado sera enviado ao iPro.")
print("Ctrl+C para parar")
print("=" * 60)

try:
    while True:

        dados = ser.read(256)

        if dados:
            print(
                time.strftime("%H:%M:%S"),
                "|",
                dados.hex(" ")
            )

except KeyboardInterrupt:
    print("\nMonitor encerrado.")

finally:
    ser.close()