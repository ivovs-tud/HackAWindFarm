"""Sample attack-side client for exercising the binary protocol."""
import logging
import math
logging.basicConfig(level=logging.WARNING, format='[%(asctime)s] %(levelname)s: %(message)s')

from AttackInterface import AttackInterface

def attack_function(data_received: dict[list[float]], attacks: dict[list[float]], time_ms: int):

    logging.debug(data_received)
    # attacks = data_received
    for i in range(9):
        attacks['Yaw'][i] = 80 * math.sin(time_ms / 10000 + i)
        attacks['Power'][i] = 1e7
        # attacks['Yaw'][i] = 40


if __name__ == "__main__":
    SERVER_IP = "localhost"  # replace with your PC1 IP
    PORT      = 9002
    
    try:
        attack_interface = AttackInterface()
        attack_interface.connect(SERVER_IP, PORT)
        attack_interface.configure(team_name="PythonAttackClient")

        ## Configure which communication lines should be tapped or have false data injection (FDI) attacks. 
        attack_interface.tap_communication(list(attack_interface._TEXT2TYPE.keys()), [1,1,1,1,1,1,1,1,1])
        attack_interface.fdi_communication(['Yaw', 'Power'], [1,1,1,1,1,1,1,1,1])

        ## Finally, start the main loop.        
        print("Starting attack interface main loop. Press Ctrl+C to stop.")
        attack_interface.start(attack_function)
        
    except KeyboardInterrupt:
        attack_interface.stop()

    print("Attack interface stopped.")