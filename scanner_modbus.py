from pymodbus.client import ModbusSerialClient
import csv
import time

PORTA = "COM8"
SLAVE = 4

client = ModbusSerialClient(
    port=PORTA,
    baudrate=9600,
    parity="N",
    stopbits=2,
    bytesize=8,
    timeout=0.5,
)

print("Conectando...")

if not client.connect():
    print("Não conectou.")
    exit()

print("Conectado!")

dados = []

for endereco in range(0, 6000):

    if endereco % 100 == 0:
        print(f"Lendo registrador {endereco}")

    try:

        rr = client.read_holding_registers(
            address=endereco,
            count=1,
            device_id=SLAVE
        )

        if rr.isError():
            continue

        if len(rr.registers) != 1:
            continue

        dados.append([
            endereco,
            rr.registers[0]
        ])

    except Exception:
        pass

    time.sleep(0.005)

client.close()

with open("scan.csv", "w", newline="") as arq:

    writer = csv.writer(arq)

    writer.writerow([
        "Endereco",
        "Valor"
    ])

    writer.writerows(dados)

print()
print("============================")
print("SCAN FINALIZADO")
print("============================")
print("Registradores encontrados:", len(dados))
print("Arquivo salvo: scan.csv")