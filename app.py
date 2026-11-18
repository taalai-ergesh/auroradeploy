import base64
import math
import os
from datetime import datetime
from functools import wraps

import psycopg2
from flask import Flask, Response, abort, redirect, render_template, request, url_for
from markupsafe import Markup

DATABASE_URL = os.environ["DATABASE_URL"]
STORE_NAME = "Taalai's AI Hardware Co."

# Verified against current listings (see README notes in chat): RTX 5090 and RTX PRO 6000
# figures are launch MSRP (NVIDIA's own marketplace currently lists the RTX PRO 6000 higher,
# around $13,250); GB300 NVL72 pricing is a rumored range ($3.7-4M) since NVIDIA doesn't
# publish rack pricing publicly.
PRODUCTS = [
    {
        "slug": "rtx5090",
        "name": "RTX 5090",
        "category": "Desktop card",
        "price": 1999,
        "memory_gb": 32,
        "memory_type": "GDDR7",
        "watts": 575,
        "clusterable": False,
        "blurb": "A high-end desktop graphics card. The smallest, cheapest way to get real AI horsepower on your own desk.",
        "tensor_performance": "3,352 AI TOPS (FP4 sparse)",
        "best_for": "Inference & prototyping",
        "lead_time_note": "Ships from stock at most authorized retailers.",
        "in_stock": True,
        "warranty": "Manufacturer warranty applies (terms vary by reseller).",
        "sku": "GPU-RTX5090-32G",
        "rack_units": "N/A — desktop PCIe card, not rack-mounted",
        "cooling": "Air-cooled (fan design varies by add-in card partner)",
        "included_components": "GPU card only. No PSU, case, motherboard, or CPU included — this is a component for an existing system.",
        "delivery_window_note": "Typically ships within 3–10 business days from authorized retailers, subject to stock.",
        "lead_time_short": "ships in 3–10 business days",
        "good_for": [
            "Local inference and fine-tuning on models that fit in 32 GB",
            "Prototyping before committing to server-scale hardware",
            "A single-user development workstation",
        ],
        "not_good_for": [
            "Training large models from scratch",
            "Serving many concurrent users at once",
            "Any model that needs more than roughly 26 GB after working-room overhead",
        ],
        "extra_specs": [
            ("CUDA cores", "21,760"),
            ("Memory bandwidth", "1,792 GB/s"),
            ("Architecture", "Blackwell"),
            ("Form factor", "Desktop PCIe card"),
        ],
    },
    {
        "slug": "rtxpro6000",
        "name": "RTX PRO 6000 Blackwell",
        "category": "Workstation card",
        "price": 8565,
        "memory_gb": 96,
        "memory_type": "GDDR7",
        "watts": 600,
        "clusterable": False,
        "blurb": "A professional workstation card built for serious AI work — three times the memory of a desktop card in the same single slot.",
        "tensor_performance": "125 TFLOPS FP32",
        "best_for": "Inference & prototyping",
        "lead_time_note": "Ships from stock at most authorized retailers.",
        "in_stock": True,
        "warranty": "Manufacturer warranty applies (terms vary by reseller).",
        "sku": "GPU-RTXPRO6000-96G",
        "rack_units": "N/A — workstation PCIe card, not rack-mounted",
        "cooling": "Air-cooled (blower-style, designed for workstation chassis airflow)",
        "included_components": "GPU card only. No workstation chassis, PSU, or motherboard included.",
        "delivery_window_note": "Typically ships within 3–10 business days from authorized retailers, subject to stock.",
        "lead_time_short": "ships in 3–10 business days",
        "good_for": [
            "Running mid-size models (up to roughly 80 GB after overhead) on a single card",
            "Workstation-class inference without a full server",
            "Teams that need more memory than a desktop card but not a full server",
        ],
        "not_good_for": [
            "Training frontier-scale models",
            "High-concurrency production serving",
            "Multi-GPU scaling — this card does not cluster with others",
        ],
        "extra_specs": [
            ("CUDA cores", "24,064"),
            ("Memory bandwidth", "1,792 GB/s"),
            ("FP32 compute", "125 TFLOPS"),
            ("Form factor", "Workstation PCIe card"),
        ],
    },
    {
        "slug": "dgxstation-gb300",
        "name": "DGX Station (GB300)",
        "category": "Desk-side supercomputer",
        "price": 99000,
        "memory_gb": 748,
        "memory_type": "HBM3e",
        "watts": 1600,
        "clusterable": False,
        "blurb": "A single GB300 Grace Blackwell Ultra Superchip in a desk-side chassis — one coherent 748 GB memory pool shared between CPU and GPU, not multiple separate cards. Runs on standard office power.",
        "tensor_performance": "~20 petaflops FP4 (sparse)",
        "best_for": "Inference & large-scale prototyping",
        "lead_time_note": "Shipping through OEM partners (ASUS, Dell, HP, Supermicro, and others) since June 2026.",
        "in_stock": True,
        "warranty": "Manufacturer warranty applies (terms vary by OEM partner).",
        "sku": "WKS-DGXSTATION-GB300-748G",
        "rack_units": "N/A — desk-side tower, not rack-mounted",
        "cooling": "Air-cooled, designed for office environments",
        "included_components": "Complete desk-side system: Grace CPU + Blackwell Ultra GPU Superchip, unified memory, chassis, and PSU. No monitor, keyboard, or networking switch included.",
        "delivery_window_note": "4–12 week lead time depending on OEM partner, as of July 2026.",
        "lead_time_short": "4–12 week lead time",
        "good_for": [
            "Running models up to roughly 620 GB after working-room overhead on a single machine",
            "Teams that want server-class memory without datacenter power or cooling",
            "Development and inference workloads that do not need multi-node scale",
        ],
        "not_good_for": [
            "Workloads that need more than one Superchip's worth of memory — this does not cluster with other units",
            "High-concurrency production serving at scale — see the server tiers below for that",
            "Frontier-scale training runs — the rack tier exists for that",
        ],
        "extra_specs": [
            ("Superchip", "1x GB300 Grace Blackwell Ultra"),
            ("Compute", "~20 petaflops FP4 (sparse)"),
            ("Memory architecture", "Unified CPU+GPU via NVLink-C2C — not multiple separate GPU pools"),
            ("Power requirement", "Standard 120V/20A office circuit — no special power needed"),
        ],
    },
    {
        "slug": "h100x8",
        "name": "8x H100 SXM server",
        "category": "Server",
        "price": 250000,
        "memory_gb": 640,
        "memory_type": "HBM3",
        "watts": 5600,
        "clusterable": True,
        "blurb": "A full server with 8 H100 GPUs wired together with NVLink, acting as one large pool of memory and compute.",
        "tensor_performance": "~31.7 petaflops FP8 (8-GPU aggregate, sparse)",
        "best_for": "Training & large-scale inference",
        "lead_time_note": "Built to order — quoted individually, like any real datacenter server.",
        "in_stock": False,
        "warranty": "Manufacturer warranty applies (enterprise service terms vary by reseller).",
        "sku": "SRV-H100X8-640G",
        "rack_units": "8U typical (air-cooled 8-GPU HGX chassis; varies by system integrator)",
        "cooling": "Air-cooled chassis fans; liquid-cooled variants available from some integrators",
        "included_components": "Complete server: 8x H100 GPUs, dual host CPUs, redundant power supplies, and NVLink baseboard. Does not include networking switches, cabling, or rack enclosure.",
        "delivery_window_note": "Built-to-order enterprise hardware — typically an 8–16 week lead time from order confirmation, depending on allocation.",
        "lead_time_short": "8–16 week lead time",
        "good_for": [
            "Training and fine-tuning models up to several hundred billion parameters",
            "High-throughput, multi-user inference",
            "Workloads that benefit from NVLink GPU-to-GPU memory sharing",
        ],
        "not_good_for": [
            "Small teams or single-user workloads — significant overkill on price and power",
            "Budget-constrained prototyping",
            "Sites without 3-phase power and datacenter-grade cooling",
        ],
        "extra_specs": [
            ("Per-GPU memory", "80 GB HBM3"),
            ("Per-GPU bandwidth", "3.35 TB/s"),
            ("GPU-to-GPU link", "NVLink, 900 GB/s"),
            ("Form factor", "8x SXM in one server chassis"),
        ],
    },
    {
        "slug": "h200x8",
        "name": "8x H200 HGX server",
        "category": "Server",
        "price": 370000,
        "memory_gb": 1128,
        "memory_type": "HBM3e",
        "watts": 5600,
        "clusterable": True,
        "blurb": "The next generation up from the H100 server — same 8-GPU NVLink design, close to double the memory per GPU.",
        "tensor_performance": "~32 petaflops FP8 (8-GPU aggregate, sparse)",
        "best_for": "Training & large-scale inference",
        "lead_time_note": "Built to order — quoted individually, like any real datacenter server.",
        "in_stock": False,
        "warranty": "Manufacturer warranty applies (enterprise service terms vary by reseller).",
        "sku": "SRV-H200X8-1128G",
        "rack_units": "8U typical (air-cooled 8-GPU HGX chassis; varies by system integrator)",
        "cooling": "Air-cooled chassis fans; liquid-cooled variants available from some integrators",
        "included_components": "Complete server: 8x H200 GPUs, dual host CPUs, redundant power supplies, and NVLink baseboard. Does not include networking switches, cabling, or rack enclosure.",
        "delivery_window_note": "Built-to-order enterprise hardware — typically an 8–16 week lead time from order confirmation, depending on allocation.",
        "lead_time_short": "8–16 week lead time",
        "good_for": [
            "Same workloads as the H100 server, with more memory headroom per GPU",
            "Larger context windows or bigger batch sizes at the same GPU count",
            "Training runs that were memory-constrained on H100",
        ],
        "not_good_for": [
            "Small teams or single-user workloads",
            "Cases where H100 pricing and availability already meet the need",
        ],
        "extra_specs": [
            ("Per-GPU memory", "141 GB HBM3e"),
            ("Per-GPU bandwidth", "4.8 TB/s"),
            ("GPU-to-GPU link", "NVLink, 900 GB/s"),
            ("Aggregate FP8 compute", "~32 petaflops"),
        ],
    },
    {
        "slug": "gb300nvl72",
        "name": "GB300 NVL72 rack",
        "category": "Rack",
        "price": 3700000,
        "memory_gb": 20700,
        "memory_type": "HBM3e",
        "watts": 135000,
        "clusterable": True,
        "blurb": "An entire rack: 72 Blackwell Ultra GPUs wired together as a single giant machine. The top of NVIDIA's current lineup.",
        "tensor_performance": "~1,440 petaflops FP4 (rack aggregate, sparse)",
        "best_for": "Large-scale training & frontier models",
        "lead_time_note": "Built to order — quoted individually, typically the longest lead time in the catalog.",
        "in_stock": False,
        "warranty": "Manufacturer warranty applies (enterprise service terms vary by reseller).",
        "sku": "RCK-GB300NVL72-72GPU",
        "rack_units": "48U (full rack)",
        "cooling": "Fully liquid-cooled (direct-to-chip), requires facility chilled-water connection",
        "included_components": "Complete rack: 72 GPU trays, Grace CPUs, NVLink switch trays, in-rack power shelves, and liquid-cooling manifolds. Does not include facility power distribution, chilled-water plant connections, or InfiniBand fabric beyond the rack.",
        "delivery_window_note": "Built-to-order; this is NVIDIA's highest-demand SKU, so lead times of 6 months or more are common industry-wide as of 2026.",
        "lead_time_short": "6+ month lead time",
        "good_for": [
            "Frontier-scale model training across dozens of GPUs acting as one machine",
            "Organizations with dedicated datacenter power, cooling, and networking",
            "Workloads that need tens of terabytes of pooled GPU memory",
        ],
        "not_good_for": [
            "Any organization without existing datacenter infrastructure",
            "Startups or teams without a dedicated facilities/ops team",
            "Workloads that fit comfortably on a single 8-GPU server — this is substantial overkill",
        ],
        "extra_specs": [
            ("GPUs per rack", "72 Blackwell Ultra + 36 Grace CPUs"),
            ("Aggregate memory bandwidth", "569 TB/s"),
            ("Cooling", "Fully liquid-cooled"),
            ("Form factor", "Full 48U datacenter rack"),
        ],
    },
]
PRODUCTS_BY_SLUG = {p["slug"]: p for p in PRODUCTS}

MODELS = [
    {
        "slug": "qwen35-397b",
        "name": "Qwen3.5-397B",
        "total_params_b": 397,
        "active_params_b": None,
        "license": "Apache 2.0",
        "source": "arena.ai/leaderboard/agent (Open Source filter)",
    },
    {
        "slug": "deepseek-v3.2",
        "name": "DeepSeek-V3.2",
        "total_params_b": 671,
        "active_params_b": 37,
        "license": "MIT License",
        "source": "arena.ai/leaderboard/agent (Open Source filter)",
    },
    {
        "slug": "kimi-k2.6",
        "name": "Kimi K2.6",
        "total_params_b": 1000,
        "active_params_b": 32,
        "license": "Modified MIT (open weights)",
        "source": "arena.ai/leaderboard/agent (Open Source filter)",
    },
]
MODELS_BY_SLUG = {m["slug"]: m for m in MODELS}

# A wider reference list for the "Can my model run?" picker on the model advisor page —
# well-known released models most people recognize by name but wouldn't know the exact
# parameter count of. Real, publicly documented figures only; not part of the 3 featured
# leaderboard models above, which are handled separately as MODELS.
WELL_KNOWN_MODELS = [
    {"name": "Llama 3.1 8B", "total_params_b": 8, "active_params_b": None},
    {"name": "Gemma 2 9B", "total_params_b": 9, "active_params_b": None},
    {"name": "Gemma 2 27B", "total_params_b": 27, "active_params_b": None},
    {"name": "Mixtral 8x7B", "total_params_b": 46.7, "active_params_b": 12.9},
    {"name": "Llama 3.1 70B", "total_params_b": 70, "active_params_b": None},
    {"name": "Qwen2.5 72B", "total_params_b": 72, "active_params_b": None},
    {"name": "Mixtral 8x22B", "total_params_b": 141, "active_params_b": 39},
    {"name": "Llama 3.1 405B", "total_params_b": 405, "active_params_b": None},
]

WORKING_ROOM_MULTIPLIER = 1.2  # +20% working room on top of raw parameter memory
HOME_WATTS = 1200  # rough continuous draw of an average home
EV_BATTERY_KWH = 90  # rough usable capacity of an electric car battery
ELECTRICITY_RATE_PER_KWH = 0.13  # US average commercial rate, EIA, disclosed estimate — varies by region/contract
STANDARD_CIRCUIT_WATTS = 1920  # 120V/20A US household circuit at NEC's 80% continuous-load rule
SPEC_DATE = "July 2026"  # last date specs/pricing were checked against public listings

REQUEST_STATUSES = ("New", "Reviewed", "Contacted")


def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_pass = os.environ.get("ADMIN_PASSWORD", "")
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Basic "):
            try:
                credentials = base64.b64decode(auth[6:]).decode()
                _, password = credentials.split(":", 1)
                if not admin_pass or password == admin_pass:
                    return f(*args, **kwargs)
            except Exception:
                pass
        elif not admin_pass:
            return f(*args, **kwargs)
        return Response(
            "Admin access required.",
            401,
            {"WWW-Authenticate": 'Basic realm="Admin"'},
        )
    return decorated

GLOSSARY = {
    "GDDR7": "A fast memory type used on desktop and workstation graphics cards. Cheaper per gigabyte than the HBM used in datacenter GPUs, but with less total bandwidth.",
    "HBM3": "\"High Bandwidth Memory\" — memory stacked directly on the GPU chip itself for very fast, very close access. Used in datacenter GPUs like the H100, not desktop cards.",
    "HBM3e": "An upgraded version of HBM3 with more capacity and bandwidth per GPU. Used in newer datacenter GPUs like the H200 and the Blackwell Ultra chips in the GB300.",
    "NVLink": "NVIDIA's high-speed direct connection between GPUs in the same server — much faster than a normal PCIe slot connection, so the GPUs can share memory and work almost as if they were one big GPU.",
    "InfiniBand": "A high-speed networking technology used to connect separate servers together in a datacenter cluster — the equivalent of NVLink, but between whole machines instead of GPUs on one board.",
    "SXM": "A physical GPU form factor used in datacenter servers, built for maximum power and NVLink bandwidth — different from the PCIe card format used in desktops and workstations.",
    "HGX": "NVIDIA's reference design for a server \"baseboard\" that holds 8 datacenter GPUs wired together with NVLink. Server makers build complete servers around an HGX board.",
    "mixture of experts": "An AI model design that splits its knowledge into many specialized \"expert\" sub-networks. Only a handful of experts activate for any given word, so it computes faster than its size suggests — but all the experts still have to be sitting in memory, ready to be picked.",
    "20% working room": "Extra memory on top of the raw model weights, reserved for what a model needs while actually generating text — things like the KV cache and activation buffers. Real deployments almost never fit with zero headroom.",
    "price-sourcing": "Checked against NVIDIA's own product listings and major retailers (B&H, Micro Center, NVIDIA's marketplace) as of July 2026 — real published prices, not estimates.",
    "Parameters (billions)": "A model's total parameter count, in billions — the \"B\" in a name like Qwen3.5-397B (397 billion). This is the single number that determines how much memory the model needs: roughly 2 GB of memory per billion parameters at standard 16-bit precision (or ~1 GB at 8-bit, ~0.5 GB at 4-bit).",
    "Precision": "How many bits are used to store each parameter. 16-bit is the common default and the safest estimate; 8-bit and 4-bit are \"quantized\" versions that use fewer bits per parameter, which shrinks memory needs roughly in proportion (8-bit ≈ half the memory, 4-bit ≈ a quarter) but can reduce output quality somewhat. See the Quantization section below for the full explanation.",
}


def glossary_term_html(term_key, label=None):
    text = GLOSSARY[term_key]
    label = label or term_key
    return Markup(
        '<span class="term" tabindex="0">{}<span class="info-dot">i</span>'
        '<span class="tooltip-bubble">{}</span></span>'
    ).format(label, text)


def required_memory_gb(model):
    return model["total_params_b"] * 1.0 * WORKING_ROOM_MULTIPLIER


def build_catalog_json():
    return [
        {
            "slug": p["slug"],
            "name": p["name"],
            "category": p["category"],
            "price": p["price"],
            "memory_gb": p["memory_gb"],
            "watts": p["watts"],
            "clusterable": p["clusterable"],
        }
        for p in PRODUCTS
    ]


def build_known_models_json():
    known = [
        {"name": m["name"], "total_params_b": m["total_params_b"], "active_params_b": m["active_params_b"]}
        for m in MODELS
    ] + WELL_KNOWN_MODELS
    known.sort(key=lambda m: m["total_params_b"])
    return known


def power_context(watts):
    daily_kwh = watts * 24 / 1000
    monthly_kwh = daily_kwh * 30
    return {
        "watts": watts,
        "home_equivalents": watts / HOME_WATTS,
        "daily_kwh": daily_kwh,
        "ev_batteries_per_day": daily_kwh / EV_BATTERY_KWH,
        "monthly_kwh": monthly_kwh,
        "monthly_electricity_cost": monthly_kwh * ELECTRICITY_RATE_PER_KWH,
    }


def power_requirement_note(watts):
    circuits_needed = math.ceil(watts / STANDARD_CIRCUIT_WATTS)
    if watts <= STANDARD_CIRCUIT_WATTS:
        return (
            "Draws {:,.0f} W — fits within a single standard 120V/20A circuit ({:,.0f} W safe "
            "continuous per NEC's 80% rule). No special electrical work needed."
        ).format(watts, STANDARD_CIRCUIT_WATTS)
    return (
        "Draws {:,.0f} W — {}x what a single standard 120V/20A circuit can safely carry "
        "continuously ({:,.0f} W). Requires 208V/240V power distribution and, at this scale, "
        "dedicated cooling — standard in datacenters, not offices or homes."
    ).format(watts, circuits_needed, STANDARD_CIRCUIT_WATTS)


def find_build(required_gb):
    candidates = []
    for p in PRODUCTS:
        if p["memory_gb"] >= required_gb:
            candidates.append({"product": p, "count": 1})
        elif p["clusterable"]:
            count = math.ceil(required_gb / p["memory_gb"])
            if count >= 2:
                candidates.append({"product": p, "count": count})

    if not candidates:
        return None

    for c in candidates:
        c["total_memory_gb"] = c["product"]["memory_gb"] * c["count"]
        c["total_price"] = c["product"]["price"] * c["count"]
        c["total_watts"] = c["product"]["watts"] * c["count"]
        c["is_cluster"] = c["count"] > 1

    candidates.sort(key=lambda c: c["total_price"])
    best = candidates[0]
    best["power"] = power_context(best["total_watts"])
    return best


def build_label(build):
    if build["count"] == 1:
        return "1x " + build["product"]["name"]
    return str(build["count"]) + "x " + build["product"]["name"]


def chart_bars(products, value_key, formatter):
    values = [p[value_key] for p in products]
    lo, hi = math.log10(min(values)), math.log10(max(values))
    span = hi - lo
    bars = []
    for p in products:
        v = p[value_key]
        pct = round(100.0 if span == 0 else max(4.0, (math.log10(v) - lo) / span * 100.0), 1)
        bars.append({"slug": p["slug"], "name": p["name"], "value": v, "pct": pct, "label": formatter(v)})
    return bars


def fmt_price(v):
    return "${:,.0f}".format(v)


def fmt_memory(v):
    return "{:.1f} TB".format(v / 1000) if v >= 1000 else "{:.0f} GB".format(v)


def fmt_watts(v):
    return "{:.1f} kW".format(v / 1000) if v >= 1000 else "{:.0f} W".format(v)


def ensure_schema():
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS quote_requests (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                contact TEXT NOT NULL,
                build_description TEXT NOT NULL,
                total_price NUMERIC,
                submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("ALTER TABLE quote_requests ADD COLUMN IF NOT EXISTS total_watts NUMERIC")
        cur.execute("ALTER TABLE quote_requests ADD COLUMN IF NOT EXISTS product_slug TEXT")
        cur.execute("ALTER TABLE quote_requests ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'New'")
        conn.commit()


ensure_schema()

app = Flask(__name__)
app.jinja_env.globals.update(
    STORE_NAME=STORE_NAME,
    HOME_WATTS=HOME_WATTS,
    EV_BATTERY_KWH=EV_BATTERY_KWH,
    ELECTRICITY_RATE_PER_KWH=ELECTRICITY_RATE_PER_KWH,
    STANDARD_CIRCUIT_WATTS=STANDARD_CIRCUIT_WATTS,
    SPEC_DATE=SPEC_DATE,
    term=glossary_term_html,
    NAV_PRODUCTS=[{"slug": p["slug"], "name": p["name"], "category": p["category"]} for p in PRODUCTS],
)


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, title="Page not found",
                            message="That page doesn't exist — it may have moved, or the link was mistyped."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, title="Something went wrong",
                            message="An unexpected error occurred on our end. Nothing was charged or submitted."), 500


@app.route("/")
def home():
    charts = {
        "price": chart_bars(PRODUCTS, "price", fmt_price),
        "memory": chart_bars(PRODUCTS, "memory_gb", fmt_memory),
        "power": chart_bars(PRODUCTS, "watts", fmt_watts),
    }
    meters_by_slug = {
        p["slug"]: {
            "memory_pct": next(b["pct"] for b in charts["memory"] if b["slug"] == p["slug"]),
            "power_pct": next(b["pct"] for b in charts["power"] if b["slug"] == p["slug"]),
            "price_pct": next(b["pct"] for b in charts["price"] if b["slug"] == p["slug"]),
        }
        for p in PRODUCTS
    }
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM quote_requests")
        (request_count,) = cur.fetchone()
    total_gpu_memory_gb = sum(p["memory_gb"] for p in PRODUCTS)

    example_model = MODELS_BY_SLUG["deepseek-v3.2"]
    example_req_gb = required_memory_gb(example_model)
    example_startup = find_build(example_req_gb)
    example_scale = find_build(example_req_gb * 2)
    example_builds = {
        "model": example_model,
        "required_gb": example_req_gb,
        "startup": {"build": example_startup, "label": build_label(example_startup) if example_startup else None},
        "scale": {"build": example_scale, "label": build_label(example_scale) if example_scale else None},
    }

    return render_template(
        "home.html",
        products=PRODUCTS,
        power_context=power_context,
        total_gpu_memory_gb=total_gpu_memory_gb,
        charts=charts,
        meters_by_slug=meters_by_slug,
        request_count=request_count,
        example_builds=example_builds,
        catalog_json=build_catalog_json(),
        known_models_json=build_known_models_json(),
        working_room_multiplier=WORKING_ROOM_MULTIPLIER,
        home_watts=HOME_WATTS,
    )


@app.route("/models")
def models():
    rows = []
    for m in MODELS:
        req_gb = required_memory_gb(m)
        build = find_build(req_gb)
        rows.append({"model": m, "required_gb": req_gb, "build": build, "build_label": build_label(build) if build else None})

    catalog_json = build_catalog_json()
    known_models_json = build_known_models_json()
    return render_template(
        "models.html",
        rows=rows,
        catalog_json=catalog_json,
        known_models_json=known_models_json,
        working_room_multiplier=WORKING_ROOM_MULTIPLIER,
        home_watts=HOME_WATTS,
        ev_battery_kwh=EV_BATTERY_KWH,
    )


@app.route("/configurator")
def configurator():
    catalog_json = build_catalog_json()
    models_json = [
        {"slug": m["slug"], "name": m["name"], "total_params_b": m["total_params_b"], "active_params_b": m["active_params_b"]}
        for m in MODELS
    ]
    return render_template(
        "configurator.html",
        catalog_json=catalog_json,
        models_json=models_json,
        working_room_multiplier=WORKING_ROOM_MULTIPLIER,
        home_watts=HOME_WATTS,
        ev_battery_kwh=EV_BATTERY_KWH,
        electricity_rate=ELECTRICITY_RATE_PER_KWH,
    )


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/technical-guide")
def technical_guide():
    catalog_json = build_catalog_json()
    return render_template(
        "technical_guide.html",
        catalog_json=catalog_json,
        working_room_multiplier=WORKING_ROOM_MULTIPLIER,
        home_watts=HOME_WATTS,
        standard_circuit_watts=STANDARD_CIRCUIT_WATTS,
    )


@app.route("/product/<slug>")
def product_detail(slug):
    product = PRODUCTS_BY_SLUG.get(slug)
    if not product:
        abort(404)
    pc = power_context(product["watts"])
    power_note = power_requirement_note(product["watts"])

    compatibility = []
    for m in MODELS:
        req_gb = required_memory_gb(m)
        if product["memory_gb"] >= req_gb:
            compatibility.append({"model": m, "can_run": True, "required_gb": req_gb, "note": "Runs on a single unit."})
        elif product["clusterable"]:
            count = math.ceil(req_gb / product["memory_gb"])
            compatibility.append({
                "model": m, "can_run": None, "required_gb": req_gb,
                "note": "Needs {}x units clustered together (not a single unit).".format(count),
            })
        else:
            compatibility.append({"model": m, "can_run": False, "required_gb": req_gb, "note": "Does not have enough memory, and this product does not cluster."})

    power_pct = next(b["pct"] for b in chart_bars(PRODUCTS, "watts", fmt_watts) if b["slug"] == slug)

    return render_template(
        "product_detail.html", p=product, pc=pc, power_note=power_note, compatibility=compatibility, power_pct=power_pct
    )


@app.route("/compare")
def compare():
    requested = [s for s in request.args.get("slugs", "").split(",") if s]
    slugs = [s for s in requested if s in PRODUCTS_BY_SLUG]
    seen = []
    for s in slugs:
        if s not in seen:
            seen.append(s)
    products = [PRODUCTS_BY_SLUG[s] for s in seen[:3]]
    unavailable_count = len(set(requested) - set(seen))

    extra_labels = []
    for p in products:
        for label, _ in p["extra_specs"]:
            if label not in extra_labels:
                extra_labels.append(label)
    extra_rows = [
        (label, [dict(p["extra_specs"]).get(label, "—") for p in products])
        for label in extra_labels
    ]

    bars_by_slug = {}
    if len(products) >= 2:
        for key in ("price", "memory_gb", "watts"):
            bars = chart_bars(products, key, lambda v: "")
            for b in bars:
                bars_by_slug.setdefault(b["slug"], {})[key] = b["pct"]

    badges_by_slug = {}
    if len(products) >= 2:
        cheapest_price = min(p["price"] for p in products)
        most_memory = max(p["memory_gb"] for p in products)
        most_watts = max(p["watts"] for p in products)
        for p in products:
            badges = []
            if p["price"] == cheapest_price:
                badges.append("Cheapest here")
            if p["memory_gb"] == most_memory:
                badges.append("Most memory")
            if p["watts"] == most_watts and most_watts >= 5000:
                badges.append("Enterprise beast")
            badges_by_slug[p["slug"]] = badges

    return render_template(
        "compare.html",
        products=products,
        extra_rows=extra_rows,
        power_context=power_context,
        unavailable_count=unavailable_count,
        badges_by_slug=badges_by_slug,
        bars_by_slug=bars_by_slug,
    )


@app.route("/guide")
def guide():
    return render_template("guide.html")


@app.route("/guide/<path>")
def guide_pick_model(path):
    if path not in ("startup", "scale"):
        abort(404)
    return render_template("guide_pick_model.html", path=path, models=MODELS)


@app.route("/guide/<path>/<model_slug>")
def guide_result(path, model_slug):
    if path not in ("startup", "scale"):
        abort(404)
    model = MODELS_BY_SLUG.get(model_slug)
    if not model:
        abort(404)

    req_gb = required_memory_gb(model)
    target_gb = req_gb if path == "startup" else req_gb * 2
    build = find_build(target_gb)

    return render_template(
        "guide_result.html",
        path=path,
        model=model,
        required_gb=req_gb,
        target_gb=target_gb,
        build=build,
        build_label=build_label(build) if build else None,
    )


@app.route("/quote", methods=["GET", "POST"])
def quote():
    if request.method == "GET":
        build_description = request.args.get("build", "")
        total_price = request.args.get("price", "")
        watts = request.args.get("watts", "")
        slug = request.args.get("slug", "")
        if slug and slug not in PRODUCTS_BY_SLUG:
            slug = ""
        return render_template(
            "quote.html", build_description=build_description, total_price=total_price, watts=watts, slug=slug
        )

    name = (request.form.get("name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    build_description = (request.form.get("build_description") or "").strip() or "Custom request (no specific build selected)"
    total_price_raw = request.form.get("total_price") or None
    watts_raw = request.form.get("watts") or None
    slug = request.form.get("slug") or None
    if slug and slug not in PRODUCTS_BY_SLUG:
        slug = None

    errors = {}
    if not name:
        errors["name"] = "Enter your name."
    if not contact:
        errors["contact"] = "Enter an email or phone number so we can reach you."
    elif "@" not in contact and len(contact) < 7:
        errors["contact"] = "Enter a valid email address or phone number."

    if errors:
        return render_template(
            "quote.html",
            errors=errors,
            name=name,
            build_description=build_description,
            total_price=total_price_raw or "",
            watts=watts_raw or "",
            slug=slug or "",
        )

    total_price = None
    if total_price_raw:
        try:
            total_price = float(total_price_raw)
        except ValueError:
            total_price = None

    total_watts = None
    if watts_raw:
        try:
            total_watts = float(watts_raw)
        except ValueError:
            total_watts = None

    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO quote_requests (name, contact, build_description, total_price, total_watts, product_slug)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (name, contact, build_description, total_price, total_watts, slug),
        )
        (new_id,) = cur.fetchone()
        conn.commit()

    product = PRODUCTS_BY_SLUG.get(slug)
    power = power_context(total_watts) if total_watts else None
    delivery_note = product["delivery_window_note"] if product else (
        "In-stock components typically ship within 3–10 business days; built-to-order systems "
        "typically take 8–16 weeks. Contact us after submitting for an exact estimate on custom builds."
    )

    return render_template(
        "quote_confirmation.html",
        request_id=new_id,
        build_description=build_description,
        power=power,
        delivery_note=delivery_note,
        total_price=total_price,
    )


@app.route("/requests")
@_admin_required
def requests_list():
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, contact, build_description, total_price, submitted_at, status "
            "FROM quote_requests ORDER BY id DESC"
        )
        rows = cur.fetchall()

    items = [
        {
            "id": r[0],
            "name": r[1],
            "contact": r[2],
            "build_description": r[3],
            "total_price": r[4],
            "submitted_at": r[5],
            "status": r[6],
        }
        for r in rows
    ]
    return render_template("requests.html", items=items, statuses=REQUEST_STATUSES)


@app.route("/requests/<int:request_id>/status", methods=["POST"])
@_admin_required
def update_request_status(request_id):
    new_status = request.form.get("status")
    if new_status not in REQUEST_STATUSES:
        abort(400)
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("UPDATE quote_requests SET status = %s WHERE id = %s", (new_status, request_id))
        conn.commit()
    return redirect(url_for("requests_list"))


@app.route("/requests/<int:request_id>/print")
@_admin_required
def print_quote(request_id):
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, contact, build_description, total_price, total_watts, product_slug, submitted_at, status "
            "FROM quote_requests WHERE id = %s",
            (request_id,),
        )
        row = cur.fetchone()

    if not row:
        abort(404)

    item = {
        "id": row[0],
        "name": row[1],
        "contact": row[2],
        "build_description": row[3],
        "total_price": row[4],
        "total_watts": row[5],
        "product_slug": row[6],
        "submitted_at": row[7],
        "status": row[8],
    }
    product = PRODUCTS_BY_SLUG.get(item["product_slug"])
    power = power_context(float(item["total_watts"])) if item["total_watts"] else None
    delivery_note = product["delivery_window_note"] if product else None

    return render_template(
        "quote_print.html", item=item, power=power, delivery_note=delivery_note, generated_at=datetime.now()
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
