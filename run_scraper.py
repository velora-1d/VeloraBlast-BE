import json
import os
import sys
import subprocess

def check_config():
    config_file = "env_parameters.json"
    if not os.path.exists(config_file):
        print(f"❌ Error: {config_file} not found!")
        return False
    
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
        
        # Check for placeholders
        placeholders = ["YOUR_API_KEY_HERE", "YOUR_WA_NUMBER_HERE"]
        errors = []
        for key, value in config.items():
            if str(value) in placeholders:
                errors.append(f"⚠️  {key} masih default ('{value}')")
        
        if errors:
            print("\n🛑 Konfigurasi Belum Lengkap:")
            for err in errors:
                print(err)
            print("\nSilakan edit file 'env_parameters.json' dulu ya!")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error reading config: {e}")
        return False

def main():
    print("=== Google Maps Scraper Setup Check ===")
    if check_config():
        print("\n✅ Konfigurasi aman. Menjalankan scraper...")
        try:
            # Run the main script
            subprocess.run([sys.executable, "script_initial_contact.py"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Scraper error: {e}")
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
    else:
        print("\n❌ Gagal menjalankan scraper karena konfigurasi belum sesuai.")

if __name__ == "__main__":
    main()
