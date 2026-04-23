# NJ Transit Sustainability Vendor Selection

## Project Overview

This project focuses on sustainable sourcing for NJ Transit in preparation for the FIFA World Cup 2026, where increased demand is expected to place significant pressure on operations and service reliability.

The objective is to evaluate and compare vendors for rail parts procurement by analyzing trade-offs between cost, delivery performance, environmental impact, and ordering constraints. The approach supports vendor selection through a structured, data-driven framework rather than relying solely on cost-based decisions.

This analysis supports vendor selection decisions for NJ Transit under high-demand conditions expected during FIFA 2026.

---

## Objective

The primary objective is to identify the most suitable vendor(s) by balancing three key dimensions:

- Environmental impact  
- Economic cost  
- Operational performance  

The analysis reflects real-world supply chain decision-making, where trade-offs between these factors must be carefully managed.

---

## Key Performance Indicators (KPIs)

Vendor performance is evaluated using four primary KPIs, selected based on both supply chain relevance and data availability:

### 1. CO₂ Emissions  
CO₂ Emissions = CO₂ per kg × Unit Weight × Quantity Needed  

Measures the environmental impact associated with sourcing from each vendor.

---

### 2. Total Cost  
Total Cost = (Purchase Price × Quantity Needed) + (Shipping Cost per kg × Unit Weight × Quantity Needed) + In-Transit Costs  

Represents the total procurement cost, including both product and logistics components.

---

### 3. Lead Time  
Lead Time = Lead Time (days)  

Reflects delivery performance and the ability to meet operational requirements without delays.

---

### 4. MOQ Impact  
MOQ Impact = MOQ ÷ Quantity Needed  

Captures ordering constraints. Higher values indicate reduced flexibility and potential for excess inventory and increased storage requirements.

---

## Methodology

### KPI Selection

KPI selection was guided by two criteria:

1. Relevance to supply chain performance  
2. Measurability using the available dataset  

A baseline supply chain model in AnyLogistix was used to observe key performance drivers, including cost, lead time, transportation activity, and inventory behavior. These drivers were then mapped to dataset variables to define the final KPIs.

---

### Data Processing (`vendor_data.py`)

- Processes and cleans the input dataset  
- Computes KPI values at the row level  
- Aggregates vendor-level performance metrics  
- Prepares structured data for analysis  

---

### Vendor Scoring (`scorecard.py`)

- Normalizes KPI values for comparability  
- Evaluates vendors across three dimensions:
  - Environmental  
  - Economic  
  - Social  
- Computes a composite score to rank vendors  

---

### Simulation (`simulation.py`)

- Simulates procurement over a 90-day operational horizon  
- Incorporates demand variability and lead time uncertainty  
- Estimates:
  - stockout risk  
  - penalty exposure  
  - warehouse utilization  

This step evaluates vendor performance under realistic operating conditions.

---

### Visualization (`dashboard.py`)

- Provides an interactive dashboard for analysis  
- Displays KPI comparisons and vendor rankings  
- Highlights trade-offs across key metrics  
- Supports scenario-based evaluation using adjustable weights  

---

## Social Pillar Approach

Due to the absence of verified certification data, social performance is evaluated using proxy indicators:

- Domestic sourcing (U.S.-based vs. non-U.S. vendors)  
- Operational responsibility inferred from performance metrics  
- Competitive participation signals from the dataset  

These indicators are informed by general principles from ISO 26000 and ISO 45001, without assuming formal certification.

---

## Decision Framework

Each vendor is evaluated using a weighted combination of:

- Environmental performance (CO₂ emissions)  
- Economic performance (total cost and MOQ impact)  
- Social indicators  

The final selection is based on the composite score, representing overall sustainability performance.

---

## Repository Structure

- `vendor_data.py` — Data preparation and KPI computation  
- `scorecard.py` — Vendor scoring and ranking  
- `simulation.py` — Operational simulation and risk analysis  
- `dashboard.py` — Visualization and interactive analysis  

---

## Workflow

Raw dataset  
→ KPI computation  
→ Vendor scoring  
→ Simulation  
→ Visualization  
→ Final vendor comparison  

---

## Key Insight

Vendor selection inherently involves trade-offs. Lower cost options may result in higher emissions, while faster delivery may increase logistical impact. This model is designed to make these trade-offs explicit and support balanced, informed decision-making.

---

## Conclusion

This project demonstrates a structured approach to integrating sustainability into procurement decisions. By combining data processing, simulation, and visualization, it provides a practical framework for evaluating vendors under operational constraints and uncertainty.