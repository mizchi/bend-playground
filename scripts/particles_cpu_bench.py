"""Compare flat Bend CPU and independent C loops with matched ranges/workers."""
from particles_bench import main

if __name__ == '__main__':
    main(cpu_comparison=True)
