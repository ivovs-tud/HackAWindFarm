"""Sample attack-side client for exercising the binary protocol."""

import logging
import math

from AttackInterface import AttackInterface

# The logging level can be changed to `logging.DEBUG` for more information or be saved to a file
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

# Variables which are saved in between calls (you can define your own as well)
avg_power_after_3_secs: float = float('nan')
...


def attack_function(data_received: dict[list[float]], attacks: dict[list[float]], time_ms: int):
    # Load the persistent variables
    global avg_power_after_3_secs
    ...

    logging.debug(data_received)

    for i in range(9):
        attacks['Yaw'][i] = 80 * math.sin(time_ms / 10000 + i)
        attacks['Power'][i] = 1e7
    
    # Save some values to memory (to be used later)
    if (time_ms / 1000) > 3 and math.isnan(avg_power_after_3_secs):
        avg_power_after_3_secs = sum(data_received['Power']) / len(data_received['Power'])

    print(f"t={time_ms / 1000:.1f}, avg power after 3 secs: {avg_power_after_3_secs:_.0f} (in W)")



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