"""
Police Workforce Allocation ILP

Uses three workforce pools:
- Pool 1: Warranted Officers (Patrol)
- Pool 2: Police Staff (Investigators)  
- Pool 3: PCSOs (Community)

Each pool runs an independent ILP with:
- Crime-type specific demand from LGBM forecasts
- CCHI (Crime Harm Index) weights for demand weighting
- Target allocation proportional to harm-weighted demand
- Reallocation bounds (50%-200% of current allocation)
- Objective: Minimize deviation from target allocation

Prerequisites:
1. Install dependencies: pip install -r requirements.txt
2. forecast_2026_03_to_2027_02.csv — monthly crime forecasts per force and crime type
3. cchi_weights_by_force_category.csv — force-specific CCHI weights per crime type
4. Police_Workforce_Sep2025.csv — current FTE per force and pool
5. Run: python police_workforce_ilp.py
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pulp import LpMinimize, LpProblem, LpVariable, LpStatus, LpInteger, lpSum, value
import warnings
warnings.filterwarnings('ignore')


# configuration

FORECASTS_PATH = "forecast_2026_03_to_2027_02.csv"
CCHI_WEIGHTS_PATH = "cchi_weights_by_force_category.csv"
FTE_DATA_PATH = "Police_Workforce_Sep2025.csv"

# crime type to pool mapping
POOL_DEFINITIONS = {
    "Pool_1_Patrol": {
        "name": "Warranted Officers (Patrol)",
        "total_fte": None,  # will be set from actual data
        "crime_types": [
            "Robbery", "Criminal damage and arson", "Vehicle crime",
            "Public order", "Shoplifting", "Bicycle theft", "Anti-social behaviour"
        ]
    },
    "Pool_2_Investigators": {
        "name": "Police Staff and Designated Officers (Investigators)",
        "total_fte": None,  # will be set from actual data
        "crime_types": [
            "Violence and sexual offences", "Possession of weapons", "Burglary",
            "Drugs", "Other crime", "Other theft", "Theft from the person"
        ]
    },
    "Pool_3_PCSOs": {
        "name": "Police Community Support Officers (Community)",
        "total_fte": None,  # will be set from actual data
        "crime_types": [
            "Public order", "Shoplifting", "Bicycle theft", "Anti-social behaviour"
        ]
    }
}


def normalize_force_name(force_name):
    """Normalize force name from forecast format to weights format."""
    name = force_name
    name = name.replace("Devon & Cornwall", "Devon and Cornwall")
    # use placeholder to protect Metropolitan Police from the suffix removal below
    name = name.replace("Metropolitan Police Service", "MetropolitanPolice")
    name = name.replace(" Constabulary", "").replace(" Police", "")
    name = name.replace("MetropolitanPolice", "Metropolitan Police")
    return name


def load_cchi_weights():
    """Load CCHI weights from CSV and add Anti-social behaviour with weight 1."""
    try:
        weights_df = pd.read_csv(CCHI_WEIGHTS_PATH)
        print(f"Loaded CCHI weights for {len(weights_df)} force-crime combinations from {CCHI_WEIGHTS_PATH}")
        
        cchi_weights_by_force = {}
        for _, row in weights_df.iterrows():
            force = row['force']
            crime_type = row['crime_type']
            weight = row['cchi_days']
            if force not in cchi_weights_by_force:
                cchi_weights_by_force[force] = {}
            cchi_weights_by_force[force][crime_type] = weight
        
        # anti-social behaviour is not in the weights file so we add it manually
        for force in cchi_weights_by_force:
            cchi_weights_by_force[force]["Anti-social behaviour"] = 1.0
        
        all_crimes = set()
        for force_weights in cchi_weights_by_force.values():
            all_crimes.update(force_weights.keys())
        
        print(f"CCHI weights loaded for {len(cchi_weights_by_force)} forces and {len(all_crimes)} crime types")
        print(f"Anti-social behaviour weight set to 1.0 for all forces")
        
        return cchi_weights_by_force
        
    except FileNotFoundError:
        print(f"ERROR: {CCHI_WEIGHTS_PATH} not found!")
        raise

# reallocation bounds — no force drops below 50% or exceeds 200% of its current allocation
ALPHA = 0.50
BETA = 2.00


def load_current_fte():
    """Load current FTE allocations from CSV file."""
    try:
        fte_df = pd.read_csv(FTE_DATA_PATH)
        fte_df = fte_df.fillna(0)
        
        current_fte = {}
        for _, row in fte_df.iterrows():
            force_name = normalize_force_name(row['Force'])
            pcso_val = row['PCSOs']
            if pcso_val == 'N/A' or pd.isna(pcso_val):
                pcso_val = 0
            current_fte[force_name] = {
                'Pool_1_Patrol': row['Police Officers'],
                'Pool_2_Investigators': row['Police Staff (Warrants)'],
                'Pool_3_PCSOs': pcso_val
            }
        
        totals = {
            'Pool_1_Patrol': fte_df['Police Officers'].sum(),
            'Pool_2_Investigators': fte_df['Police Staff (Warrants)'].sum(),
            'Pool_3_PCSOs': fte_df['PCSOs'].sum()
        }
        
        print(f"Loaded FTE data for {len(current_fte)} forces from {FTE_DATA_PATH}")
        print(f"National totals from data:")
        print(f"  Pool 1 (Officers): {totals['Pool_1_Patrol']:,.0f}")
        print(f"  Pool 2 (Staff): {totals['Pool_2_Investigators']:,.0f}")
        print(f"  Pool 3 (PCSOs): {totals['Pool_3_PCSOs']:,.0f}")
        
        return current_fte, totals
        
    except FileNotFoundError:
        print(f"WARNING: {FTE_DATA_PATH} not found! Using uniform distribution placeholder.")
        return None, None


CURRENT_FTE = None
NATIONAL_TOTALS = None


def load_forecasts():
    """Load monthly forecasts and aggregate to annual with normalized force names."""
    try:
        forecasts = pd.read_csv(FORECASTS_PATH)
        print(f"Loaded {len(forecasts)} monthly forecast records from {FORECASTS_PATH}")
        
        forecasts['force'] = forecasts['force'].apply(normalize_force_name)
        
        # sum monthly figures to get annual totals per force and crime type
        annual_forecasts = forecasts.groupby(['force', 'crime_type'])['predicted_n_crimes'].sum().reset_index()
        annual_forecasts.rename(columns={'predicted_n_crimes': 'predicted_annual_crimes'}, inplace=True)
        
        print(f"Aggregated to {len(annual_forecasts)} annual forecast records")
        print(f"Forces: {annual_forecasts['force'].nunique()}, Crime types: {annual_forecasts['crime_type'].nunique()}")
        
        return annual_forecasts
        
    except FileNotFoundError:
        print(f"ERROR: {FORECASTS_PATH} not found!")
        raise


# ILP implementation

def calculate_harm_weighted_demand(forecasts_df, pool_crime_types, cchi_weights_by_force):
    """
    Calculate harm-weighted demand for each force in a pool using force-specific CCHI weights.
    
    For each force: sum(w_j * D_ij) where w_j is CCHI weight and D_ij is forecasted demand
    """
    pool_forecasts = forecasts_df[forecasts_df["crime_type"].isin(pool_crime_types)].copy()
    
    def get_weight(row):
        force = row['force']
        crime = row['crime_type']
        if force in cchi_weights_by_force and crime in cchi_weights_by_force[force]:
            return cchi_weights_by_force[force][crime]
        raise ValueError(f"No CCHI weight found for force='{force}', crime_type='{crime}'")
    
    pool_forecasts["cchi_weight"] = pool_forecasts.apply(get_weight, axis=1)
    pool_forecasts["harm_weighted_demand"] = (
        pool_forecasts["predicted_annual_crimes"] * pool_forecasts["cchi_weight"]
    )
    
    force_demand = pool_forecasts.groupby("force")["harm_weighted_demand"].sum().reset_index()
    force_demand.columns = ["force", "harm_weighted_demand"]
    
    return force_demand, pool_forecasts


def calculate_target_allocation(force_demands, total_pool_fte):
    """
    Calculate target allocation Ti for each force.
    
    Ti = (force_harm_demand / national_total_harm_demand) * total_pool_fte
    """
    national_total = force_demands["harm_weighted_demand"].sum()
    
    targets = {}
    for _, row in force_demands.iterrows():
        force = row["force"]
        harm_demand = row["harm_weighted_demand"]
        share = 0 if (pd.isna(harm_demand) or national_total <= 0) else harm_demand / national_total
        targets[force] = share * total_pool_fte
    
    return targets, national_total


def run_pool_ilp(pool_id, pool_config, forecasts_df, current_fte_dict, cchi_weights_by_force):
    """
    Run ILP for a single workforce pool.
    
    Notation:
    - xi: FTE allocated to force i (integer decision variable)
    - Ti: Target allocation for force i (proportional to harm-weighted demand)
    - Ci: Current FTE for force i
    - ei: Absolute deviation |xi - Ti| (auxiliary variable)
    
    Objective: Minimize sum(ei)
    
    Constraints:
    1. sum(xi) = sum(Ci) (budget conservation)
    2. xi >= alpha * Ci (lower reallocation bound)
    3. xi <= beta * Ci (upper reallocation bound)
    4. ei >= xi - Ti, ei >= Ti - xi (linearized absolute value)
    """
    
    pool_name = pool_config["name"]
    total_fte = pool_config["total_fte"]
    crime_types = pool_config["crime_types"]
    
    print(f"\n{'='*60}")
    print(f"ILP: {pool_name}")
    print(f"{'='*60}")
    print(f"Pool ID: {pool_id}")
    print(f"Total National FTE: {total_fte:,.0f}")
    print(f"Crime types: {len(crime_types)}")
    
    force_demands, detailed_forecasts = calculate_harm_weighted_demand(
        forecasts_df, crime_types, cchi_weights_by_force
    )
    
    # only keep forces that appear in both the forecast and FTE data
    if current_fte_dict is not None:
        forecast_forces = set(force_demands["force"].tolist())
        fte_forces = set(current_fte_dict.keys())
        
        missing_fte = forecast_forces - fte_forces
        if missing_fte:
            raise ValueError(f"Forces in forecast but missing FTE data: {sorted(missing_fte)}")
        
        forces_with_both = forecast_forces & fte_forces
        force_demands = force_demands[force_demands["force"].isin(forces_with_both)]
        print(f"Using {len(force_demands)} forces with both forecast and FTE data")
    
    forces = force_demands["force"].tolist()
    print(f"Forces in pool: {len(forces)}")
    
    # recalculate budget from only the forces being optimised so the constraint is feasible
    if current_fte_dict is not None:
        total_fte = sum(current_fte_dict[f][pool_id] for f in forces)
        print(f"Budget for {len(forces)} forces: {total_fte:,.0f}")
    
    targets, national_harm_demand = calculate_target_allocation(force_demands, total_fte)
    print(f"National harm-weighted demand: {national_harm_demand:,.0f}")
    
    if current_fte_dict is None:
        raise ValueError("No FTE data provided. Please provide current_fte_dict.")
    
    current_fte = {}
    for f in forces:
        if f not in current_fte_dict:
            raise ValueError(f"Force '{f}' missing from FTE data")
        if pool_id not in current_fte_dict[f]:
            raise ValueError(f"Force '{f}' missing pool '{pool_id}' in FTE data")
        current_fte[f] = current_fte_dict[f][pool_id]
    
    prob = LpProblem(f"Pool_{pool_id}_Allocation", LpMinimize)
    
    x = LpVariable.dicts(f"x_{pool_id}", forces, lowBound=0, cat=LpInteger)  # allocated FTE
    e = LpVariable.dicts(f"e_{pool_id}", forces, lowBound=0)                  # absolute deviation
    
    prob += lpSum([e[f] for f in forces]), f"Minimize_Deviation_{pool_id}"
    
    for f in forces:
        target = targets.get(f, 0)
        current = current_fte.get(f, 0)
        
        # forces with zero current FTE stay at zero
        if current == 0:
            prob += (x[f] == 0, f"Zero_Current_{pool_id}_{f}")
            prob += (e[f] >= -target, f"Dev_Pos_{pool_id}_{f}")
            prob += (e[f] >= target, f"Dev_Neg_{pool_id}_{f}")
            continue
        
        prob += (x[f] >= ALPHA * current, f"Lower_Bound_{pool_id}_{f}")
        prob += (x[f] <= BETA * current, f"Upper_Bound_{pool_id}_{f}")
        prob += (e[f] >= x[f] - target, f"Dev_Pos_{pool_id}_{f}")
        prob += (e[f] >= target - x[f], f"Dev_Neg_{pool_id}_{f}")
    
    # total allocation must equal total current FTE
    prob += (lpSum([x[f] for f in forces]) == total_fte, f"Budget_{pool_id}")
    
    prob.solve()
    
    if LpStatus[prob.status] != 'Optimal':
        raise RuntimeError(f"ILP did not solve optimally. Status: {LpStatus[prob.status]}")
    
    results = []
    total_deviation = 0
    
    for f in forces:
        allocated = value(x[f])
        target = targets.get(f, 0)
        deviation = value(e[f])
        current = current_fte.get(f, 0)
        demand = force_demands[force_demands["force"] == f]["harm_weighted_demand"].values[0]
        dpi = (allocated / target * 100) if target > 0 else 100
        total_deviation += deviation
        
        results.append({
            "force": f,
            "pool": pool_id,
            "pool_name": pool_name,
            "current_fte": current,
            "target_fte": target,
            "allocated_fte": allocated,
            "absolute_deviation": deviation,
            "harm_weighted_demand": demand,
            "demand_pressure_index_pct": dpi,
            "reallocation_pct": ((allocated - current) / current * 100) if current > 0 else 0
        })
    
    results_df = pd.DataFrame(results)
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {pool_name}")
    print(f"{'='*60}")
    print(f"Total absolute deviation from target: {total_deviation:,.0f}")
    print(f"Mean deviation per force: {total_deviation / len(forces):,.0f}")

    dpi = results_df["demand_pressure_index_pct"]
    print(f"\nDemand Pressure Index (DPI) summary:")
    print(f"  Mean:   {dpi.mean():>7.1f}%  (100% = perfect match to harm-weighted target)")
    print(f"  Median: {dpi.median():>7.1f}%")
    print(f"  Std:    {dpi.std():>7.1f}%")
    print(f"  Min:    {dpi.min():>7.1f}%  ({results_df.loc[dpi.idxmin(), 'force']})")
    print(f"  Max:    {dpi.max():>7.1f}%  ({results_df.loc[dpi.idxmax(), 'force']})")

    print(f"\nTop 5 forces by allocated FTE:")
    top5 = results_df.nlargest(5, "allocated_fte")
    for _, row in top5.iterrows():
        print(f"  {row['force']}: {row['allocated_fte']:.0f} FTE "
              f"(target: {row['target_fte']:.0f}, "
              f"DPI: {row['demand_pressure_index_pct']:.1f}%)")
    
    return results_df, total_deviation


def print_allocation_results(results_df, pool_name="Pool"):
    """Print detailed allocation results per force."""
    print(f"\n{'='*60}")
    print(f"DETAILED ALLOCATION BY POLICE FORCE AREA - {pool_name}")
    print(f"{'='*60}")
    
    sorted_df = results_df.sort_values("allocated_fte", ascending=False)
    
    print(f"\n{'Force Area':<35} {'Current':>10} {'Target':>10} {'Allocated':>10} {'DPI%':>8} {'Change%':>10}")
    print("-" * 100)
    
    for _, row in sorted_df.iterrows():
        print(f"{row['force']:<35} {row['current_fte']:>10.0f} {row['target_fte']:>10.0f} "
              f"{row['allocated_fte']:>10.0f} {row['demand_pressure_index_pct']:>7.1f}% "
              f"{row['reallocation_pct']:>+9.1f}%")


def plot_deviation_chart(combined_results):
    """Bar chart showing before and after deviation from harm-weighted targets per pool."""
    pool_labels = {
        "Pool_1_Patrol": "Warranted Officers\n(Patrol)",
        "Pool_2_Investigators": "Police Staff\n(Investigators)",
        "Pool_3_PCSOs": "PCSOs\n(Community)"
    }

    pools = list(pool_labels.keys())
    before_devs = []
    after_devs = []

    for pool_id in pools:
        pool_results = combined_results[combined_results["pool"] == pool_id]
        before_devs.append((pool_results["current_fte"] - pool_results["target_fte"]).abs().sum())
        after_devs.append(pool_results["absolute_deviation"].sum())

    x = np.arange(len(pools))
    width = 0.35

    fig, ax = plt.subplots(figsize=(9, 6))
    bars_before = ax.bar(x - width / 2, before_devs, width, label="Before optimisation", color="#d9534f", alpha=0.85)
    bars_after  = ax.bar(x + width / 2, after_devs,  width, label="After optimisation",  color="#5cb85c", alpha=0.85)

    ax.set_xlabel("Workforce Pool", fontsize=12)
    ax.set_ylabel("Total Absolute Deviation (FTE)", fontsize=12)
    ax.set_title("Before vs After Optimisation\nTotal Absolute Deviation from Harm-Weighted Targets", fontsize=13)
    ax.set_xticks(x)
    ax.set_xticklabels([pool_labels[p] for p in pools], fontsize=11)
    ax.legend(fontsize=11)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))

    for bar in bars_before:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
                f"{bar.get_height():,.0f}", ha="center", va="bottom", fontsize=9)
    for bar in bars_after:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
                f"{bar.get_height():,.0f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig("deviation_before_after.png", dpi=150)
    print("\nDeviation chart saved to: deviation_before_after.png")
    plt.show()


# main execution

def main():
    """Main execution pipeline — runs all three pool ILPs."""
    global CURRENT_FTE, NATIONAL_TOTALS
    
    print(f"{'='*60}")
    print("POLICE WORKFORCE ALLOCATION ILP")
    print(f"{'='*60}")
    print("Three independent ILPs - one per workforce pool")
    print(f"{'='*60}")
    
    print("\n[1/4] Loading current FTE allocations...")
    CURRENT_FTE, NATIONAL_TOTALS = load_current_fte()
    
    if NATIONAL_TOTALS:
        for pool_id in POOL_DEFINITIONS.keys():
            POOL_DEFINITIONS[pool_id]['total_fte'] = NATIONAL_TOTALS.get(pool_id, 0)
    
    print("\n[2/4] Loading CCHI weights by force and crime type...")
    cchi_weights_by_force = load_cchi_weights()
    
    print("\n[3/4] Loading crime forecasts...")
    forecasts_df = load_forecasts()
    print(f"\n      Total forces: {forecasts_df['force'].nunique()}")
    print(f"      Total crime types: {forecasts_df['crime_type'].nunique()}")
    
    print(f"\n[4/4] Running three independent ILPs (one per pool)...")
    all_results = []
    total_deviation_all_pools = 0
    
    for pool_id, pool_config in POOL_DEFINITIONS.items():
        results, deviation = run_pool_ilp(pool_id, pool_config, forecasts_df, CURRENT_FTE, cchi_weights_by_force)
        all_results.append(results)
        total_deviation_all_pools += deviation
        results.to_csv(f"{pool_id}_allocation_results.csv", index=False)
        print(f"\n      Results saved to: {pool_id}_allocation_results.csv")
    
    combined_results = pd.concat(all_results, ignore_index=True)
    combined_results.to_csv("all_pools_allocation_results.csv", index=False)
    
    print(f"\n{'='*60}")
    print("OVERALL SUMMARY - ALL THREE POOLS")
    print(f"{'='*60}")
    print(f"Total absolute deviation across all pools: {total_deviation_all_pools:,.0f}")
    print(f"\nPool summaries:")
    for pool_id, pool_config in POOL_DEFINITIONS.items():
        pool_results = combined_results[combined_results["pool"] == pool_id]
        total_fte = pool_results["current_fte"].sum()
        dev_before = (pool_results["current_fte"] - pool_results["target_fte"]).abs().sum()
        dev_after = pool_results["absolute_deviation"].sum()
        pct_reduction = (dev_before - dev_after) / dev_before * 100 if dev_before > 0 else 0
        reallocated = (pool_results["allocated_fte"] - pool_results["current_fte"]).abs().sum() / 2
        print(f"\n  {pool_config['name']}:")
        print(f"    Starting FTE (42 forces):      {total_fte:>10,.0f}")
        print(f"    FTE reallocated:               {reallocated:>10,.0f}  ({reallocated / total_fte * 100:.1f}% of pool)")
        print(f"    Deviation before optimisation: {dev_before:>10,.0f}")
        print(f"    Deviation after optimisation:  {dev_after:>10,.0f}")
        print(f"    Reduction in deviation:        {dev_before - dev_after:>10,.0f}  ({pct_reduction:.1f}% improvement)")
    
    # overall figures across all pools
    total_fte_all = combined_results["current_fte"].sum()
    dev_before_all = (combined_results["current_fte"] - combined_results["target_fte"]).abs().sum()
    dev_after_all = combined_results["absolute_deviation"].sum()
    pct_reduction_all = (dev_before_all - dev_after_all) / dev_before_all * 100 if dev_before_all > 0 else 0
    reallocated_all = (combined_results["allocated_fte"] - combined_results["current_fte"]).abs().sum() / 2

    print(f"\n{'='*60}")
    print("OVERALL (ALL POOLS COMBINED)")
    print(f"{'='*60}")
    print(f"  Total FTE across all pools:        {total_fte_all:>10,.0f}")
    print(f"  Total FTE reallocated:             {reallocated_all:>10,.0f}  ({reallocated_all / total_fte_all * 100:.1f}% of workforce)")
    print(f"  Deviation before optimisation:     {dev_before_all:>10,.0f}")
    print(f"  Deviation after optimisation:      {dev_after_all:>10,.0f}")
    print(f"  Overall reduction in deviation:    {dev_before_all - dev_after_all:>10,.0f}  ({pct_reduction_all:.1f}% improvement)")

    print(f"\nCombined results saved to: all_pools_allocation_results.csv")
    print(f"\n{'='*60}")
    print("OPTIMIZATION COMPLETE")
    print(f"{'='*60}")

    plot_deviation_chart(combined_results)


if __name__ == "__main__":
    main()
