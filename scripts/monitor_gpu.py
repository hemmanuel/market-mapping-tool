import time
import subprocess
import json
import urllib.request
import sys
import os

def get_gpu_stats():
    try:
        # Get GPU utilization and Memory usage
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(', ')
            if len(parts) == 3:
                return {
                    'utilization': f"{parts[0]}%",
                    'memory_used': f"{parts[1]} MB",
                    'memory_total': f"{parts[2]} MB"
                }
    except Exception as e:
        pass
    return None

def get_ollama_stats():
    try:
        req = urllib.request.Request('http://localhost:11434/api/ps')
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            models = data.get('models', [])
            if not models:
                return "No models loaded in Ollama"
            
            stats = []
            for model in models:
                name = model.get('name', 'Unknown')
                vram_bytes = model.get('size_vram', 0)
                vram_gb = vram_bytes / (1024**3)
                stats.append(f"Model: {name} | VRAM Allocated: {vram_gb:.2f} GB")
            return "\n".join(stats)
    except Exception as e:
        return f"Could not connect to Ollama API: {e}"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    print("Starting GPU & Ollama Monitor... (Press Ctrl+C to stop)")
    try:
        while True:
            clear_screen()
            print("="*50)
            print(" GPU & OLLAMA REAL-TIME MONITOR")
            print("="*50)
            print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            print("--- GPU STATS (RTX 5090) ---")
            gpu_stats = get_gpu_stats()
            if gpu_stats:
                print(f"Utilization: {gpu_stats['utilization']}")
                print(f"VRAM Usage:  {gpu_stats['memory_used']} / {gpu_stats['memory_total']}")
            else:
                print("Could not fetch GPU stats (is nvidia-smi available?)")
                
            print("\n--- OLLAMA STATS ---")
            print(get_ollama_stats())
            
            print("\n" + "="*50)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    main()
