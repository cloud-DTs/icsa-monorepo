import globals
import transmission

def help_menu():
  print("""
    Available commands:
      send                        - Sends payload to IoT endpoint.
      help                        - Show this help menu.
      exit                        - Exit the program.
  """)

def main():
    globals.initialize_config()

    print("Welcome to the IoT Device Simulator. Type 'help' for commands.")

    while True:
      try:
        user_input = input(">>> ").strip()
      except (EOFError, KeyboardInterrupt):
        print("\nExiting.")
        break

      if not user_input:
        continue

      parts = user_input.split()
      command = parts[0]
      args = parts[1:]

      if command == "send":
        transmission.send()
      elif command == "help":
        help_menu()
      elif command == "exit":
        print("Goodbye!")
        break
      else:
        print(f"Unknown command: {command}. Type 'help' for a list of commands.")

if __name__ == "__main__":
  main()
