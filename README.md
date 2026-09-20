# Self-Reorganizing Roads 🚦

**Adaptive allocation of urban road space using real-time traffic demand**

*Fund My Crazy 2026 — Hackathon Proof-of-Concept*

---

## ⚠ Important disclaimer

All performance figures shown in this prototype are **simulation outputs**.  
They are **not real-world measurements, field trials, or peer-reviewed results**.  
This is a proof-of-concept demonstrator, not a production traffic-control system.

---

## Problem

Urban road infrastructure is largely static.  Lane functions are painted on
asphalt and stay fixed regardless of demand.  A kerbside lane built for
right-turns sits idle during rush hour.  A general lane carries low bus
volumes while buses queue behind private vehicles.  Emergency vehicles
compete for road space instead of having a guaranteed corridor.

**The road's physical capacity is already there.  It is just permanently
allocated to the wrong purpose at the wrong time.**

---

## Solution

Treat road space as a dynamic resource.  Re-assign the *function* of existing
physical lanes in real time based on actual demand — without moving any kerbs
or building any new infrastructure.

| Condition | System action |
|---|---|
| Normal traffic | General-purpose configuration |
| High bus demand | Convert one lane to dedicated **Bus Priority** |
| Emergency vehicle | Open a protected **Emergency Corridor** |
| Pedestrian surge | Allocate a **Pedestrian Buffer** from a general lane |

> **Key distinction from adaptive traffic signals:**  
> Adaptive signals change *signal timing* on fixed lane functions.  
> Self-Reorganizing Roads changes *which function each physical lane serves*.

---

## Architecture

```
Traffic State
    ↓
Demand Estimation          (src/demand/)
    ↓
Priority Engine            (src/priority/)   ← 5-level hierarchy
    ↓
Safety Constraint Check    (src/safety/)     ← hard rules, never overridden
    ↓
Lane Allocator             (src/allocation/) ← validates + generates transition
    ↓
Simulation Update          (src/simulation/) ← queue model, metrics
    ↓
Dashboard                  (app/)            ← Streamlit visualisation
```

### Module map

```
self_reorganizing_roads/
├── app/
│   └── streamlit_app.py       # Streamlit dashboard
├── src/
│   ├── models.py              # Core data models (enums, dataclasses)
│   ├── orchestrator.py        # Wires components together per scenario
│   ├── config/
│   │   └── settings.py        # YAML config loader
│   ├── simulation/
│   │   └── traffic_simulator.py  # Macroscopic queue simulation
│   ├── demand/
│   │   └── demand_estimator.py   # Demand signal computation
│   ├── priority/
│   │   └── priority_engine.py    # Hierarchical decision logic
│   ├── safety/
│   │   └── safety_manager.py     # Hard safety constraints
│   ├── allocation/
│   │   └── lane_allocator.py     # Config validation + transition
│   ├── metrics/
│   │   └── metrics_calculator.py # Simulation-derived metrics
│   └── visualization/
│       └── road_visualizer.py    # Plotly chart helpers
├── tests/                        # pytest unit tests
├── config/
│   └── settings.yaml             # All thresholds and parameters
├── requirements.txt
└── README.md
```

---

## Technology stack

| Library | Purpose |
|---|---|
| Python 3.11+ | Core language |
| Streamlit | Dashboard / UI |
| NumPy | Simulation computation |
| Pandas | Data tables |
| Plotly | Charts and road visualisation |
| PyYAML | Configuration |
| pytest | Unit tests |

**No SUMO.  No ML model.  No database.  No cloud services required.**  
The demo runs entirely on a local machine.

---

## Installation

```bash
# 1. Clone or unzip the project
cd self_reorganizing_roads

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running the demo

```bash
# From the project root directory:
streamlit run app/streamlit_app.py
```

The dashboard opens in your browser at `http://localhost:8501`.

---

## Running the tests

```bash
# From the project root directory:
pytest tests/ -v
```

Expected output: all tests pass.  Tests verify logic, not just coverage.

---

## Demo sequence (≈ 2 minutes)

Follow these steps to demonstrate the full system to judges:

1. **Open the dashboard** — default is Normal Traffic scenario.
2. Point to the road visualisation: four lanes, all general-purpose + bicycle lane.
3. **Click "High Bus Demand"** — observe the demand indicators rising.
   - The priority engine detects bus demand exceeding the threshold.
   - The system enters TRANSITION state (safety step).
   - Lane 2 becomes **BUS PRIORITY** (amber).
4. Switch to the **Metrics tab** — show the bus queue chart diverging from baseline.
   Explain: "the baseline queue keeps growing; ours stabilises after reorganisation."
5. Return to **Dashboard** — **click "Emergency Vehicle"**.
   - The emergency detector fires.
   - Lane 1 becomes **EMERGENCY CORRIDOR** (red) with clearance timer active.
6. Point to the Decision Engine panel — read the reason aloud.
7. Switch to **Metrics tab** — show the comparison table.
8. Explain the differentiation: *"We didn't change the signal timing. We changed
   which lane serves which purpose.  That's the difference."*

---

## Scenarios

| Scenario | Arrival rates | Expected outcome |
|---|---|---|
| Normal | car 12/min, bus 1.5/min | GENERAL config maintained |
| High Bus Demand | car 10/min, bus 5.5/min | BUS_PRIORITY lane activated |
| Emergency Vehicle | car 12/min, emergency 0.8/min | EMERGENCY CORRIDOR created |
| Pedestrian Surge | car 8/min, pedestrian 22/min | PEDESTRIAN_BUFFER allocated |

---

## Priority hierarchy

```
Level 1 — SAFETY             hard constraints; falls back if violated
Level 2 — EMERGENCY          life-safety; creates protected corridor
Level 3 — PEDESTRIAN/CYCLIST protects vulnerable road users during surges
Level 4 — PUBLIC TRANSPORT   bus-priority lane when bus demand is high
Level 5 — GENERAL TRAFFIC    maintain default if no condition is triggered
```

---

## Safety model

The safety manager enforces hard constraints that **cannot be overridden**
by the priority or optimisation logic:

1. **Minimum general lanes** — at least one GENERAL lane is always available.
2. **EMERGENCY + PEDESTRIAN_BUFFER incompatibility** — these two functions
   cannot coexist in the same configuration.
3. **Single emergency corridor** — at most one EMERGENCY lane per configuration.
4. **Adjacent incompatibilities** — no two incompatible functions next to each other.

If any constraint is violated, the system immediately falls back to the
configured safe default: `[GENERAL, GENERAL, GENERAL, BICYCLE]`.

Transition states ensure lanes are never instantly reassigned.
A `TRANSITION` phase (configurable duration, default 2 steps) separates
every configuration change.

---

## Metrics

All metrics are computed from simulation state at runtime.
No values are hard-coded.

| Metric | Description |
|---|---|
| Average travel time | BPR-function estimate per vehicle type (min) |
| Queue length | Vehicles waiting at end of each step |
| Throughput | Vehicles cleared per simulation step |
| Bus delay | Average travel time above free-flow for buses |
| Total vehicles served | Cumulative throughput over scenario |

---

## Configuration

All thresholds are in `config/settings.yaml`.  No code changes are needed to
adjust the system behaviour:

```yaml
demand:
  thresholds:
    bus_priority: 4.0         # demand score to trigger bus-priority lane
    pedestrian_priority: 18.0 # demand score to trigger pedestrian buffer

lanes:
  min_general_lanes: 1
  transition_duration: 2      # steps spent in TRANSITION state

priority:
  emergency_clearance_duration: 5  # steps to hold corridor after last detection
```

---

## IMPORTANT LIMITATIONS

This is a proof-of-concept prototype built in a 3-day hackathon window.

**What this prototype does NOT model:**

- Physical lane barrier actuation time (boom gates, guided bollards)
- Variable message sign update delays
- Driver compliance and behavioural response
- Network effects (traffic diverting to parallel roads)
- Weather, incidents, special events, or day-of-week variation
- Multi-intersection coordination
- Real sensor noise, latency, or dropout
- Emergency vehicle routing beyond a single segment
- Real-world lane capacity values (capacities are illustrative)
- Pedestrian/cyclist volumes beyond a simplified flow model

**What this prototype does NOT claim:**

- Guaranteed reduction in accidents
- Guaranteed reduction in congestion
- Guaranteed improvement in emergency response times
- Real-world economic savings
- Equivalence to field-tested traffic management systems

**The simulation demonstrates that the core concept of dynamic lane
function reallocation is computationally feasible and produces
logically consistent results under the stated modelling assumptions.**

---

## Future improvements (if time permits)

| Feature | Value |
|---|---|
| SUMO integration adapter | Microscopic vehicle simulation |
| Sensor dropout simulation | Robustness testing |
| Multi-intersection coordination | Corridor-level optimisation |
| ML demand forecasting module | Proactive rather than reactive allocation |
| Real-world capacity calibration | Credible quantitative claims |
| API layer (FastAPI) | Integration with external traffic management systems |
| Historical replay mode | Demonstrate against real traffic data |

---

## 10 tough judge questions — honest answers

**Q1: How does this differ from adaptive traffic signals?**  
Adaptive signals optimise *signal timing* — green phases for existing fixed
lanes.  This system changes *which physical lane serves which purpose*.
That is a structural difference: a bus-priority lane exists even during
a red phase.

**Q2: What evidence shows this reduces congestion?**  
None from the real world.  The simulation shows that under stated modelling
assumptions, bus queues decrease when a dedicated priority lane is allocated.
Real-world validation would require a controlled field trial.

**Q3: Could this cause accidents if a driver ignores the new lane markings?**  
Yes — driver compliance is a real risk not modelled here.  In practice,
physical barriers (retractable bollards, dynamic lane-control signals) and
adequate warning time would be required.  The transition state in this model
is a simplified proxy for that safety period.

**Q4: How long does the reconfiguration actually take in the real world?**  
We model 2 simulation minutes.  Real-world variable message signs update
in seconds; overhead gantry signals in under a minute; physical guided
barriers in 2–5 minutes depending on technology.  The transition duration
is configurable.

**Q5: What happens if the sensors fail?**  
The system falls back to the pre-configured safe default configuration.
This is the last line of defence: the safe fallback is a known-safe
general-purpose configuration that does not require any sensor data.

**Q6: Why not just build more lanes?**  
Construction cost, right-of-way constraints, and induced demand.  This
approach uses existing infrastructure at higher utilisation without
physical expansion.

**Q7: Could this be gamed or hacked?**  
Cybersecurity is not modelled.  Any real deployment would require secure
communication channels, anomaly detection, and manual override capabilities.

**Q8: What is the capacity model based on?**  
Simplified illustrative values.  The Highway Capacity Manual provides
real-world capacity figures.  Calibrating to real road geometry would
be necessary before any deployment claim.

**Q9: Does this work at night or off-peak?**  
The system reverts to normal configuration when no priority condition is
detected.  Off-peak behaviour defaults to the general-purpose layout.

**Q10: Why not just use bus lanes permanently?**  
Permanent bus lanes are beneficial on high-frequency bus routes.
Dynamic allocation serves mixed-demand corridors where bus demand varies
significantly across the day, and where permanently dedicating a lane
would over-serve buses at the cost of general traffic during low-demand periods.

---

## Reproduction

```bash
# Exact commands to reproduce the demo:
pip install -r requirements.txt
pytest tests/ -v
streamlit run app/streamlit_app.py
```

Random seed is fixed at `42` in `config/settings.yaml`.
The same scenario always produces the same results.
