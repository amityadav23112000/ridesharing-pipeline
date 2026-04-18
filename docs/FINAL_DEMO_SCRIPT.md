# COMPLETE 20-MINUTE VIDEO DEMO SCRIPT
## Ridesharing Pipeline | CSG527 Cloud Computing | H20250060 | BITS Pilani Hyderabad

---

> HOW TO USE:
> - Say everything written normally out loud
> - Lines marked SHOW: tell you what to display on screen
> - Lines marked DO: tell you what to click or type
> - Speak slowly and clearly — do not rush

---

## SEGMENT 1 — INTRODUCTION
### Time: 0:00 to 2:00

SHOW: Project title on screen or clean desktop

"Hello everyone. My name is Amit Yadav. I am a student at BITS Pilani Hyderabad. My student ID is H20250060 and this project is for the course CSG527 Cloud Computing.

Today I will show you my project — a real-time ridesharing data pipeline built on Amazon Web Services.

Let me first explain the problem I am solving.

Imagine you open Ola or Uber on your phone. There are thousands of drivers moving around the city — every driver's phone sends its GPS location to the server every single second. Now the server has to answer one question very fast: in this area of the city right now, are there more passengers waiting than drivers available?

If yes — we need to increase the price. This is called surge pricing. And we need to do this in under 5 seconds. Because if it takes longer than 5 seconds, the passenger gets frustrated and cancels.

At the same time, the business also needs answers to historical questions — which city earned the most revenue yesterday? Which drivers are top performers? How does surge pricing affect cancellations?

So we have two completely different needs:
- Number one: Real-time surge detection in under 5 seconds
- Number two: Historical batch analytics for business reporting

I built a system that does both together. Let me show you how."

---

## SEGMENT 2 — ARCHITECTURE
### Time: 2:00 to 5:00

SHOW: README.md architecture diagram

"This is the architecture of my system. Let me explain it from top to bottom in simple terms.

At the very top are the GPS devices — these are the driver phones sending location every second. I have simulated this in software — I will show that live in a moment.

The first layer is the Ingestion Layer. GPS events arrive at my server and go into Apache Kafka. Kafka is like a post office — it receives messages and keeps them safely stored until someone is ready to process them. I have three Kafka topics — think of them as three different post boxes:
- gps-critical — for emergency high surge zones
- gps-surge — for zones approaching surge
- gps-normal — for regular GPS updates

Why three? Because in a real system you never want normal traffic blocking emergency messages. Critical events always get processed first.

The second layer is the Speed Layer — this is where real-time magic happens. Apache Spark reads from Kafka continuously. Every 2 to 10 seconds — depending on load — it processes a fresh batch of GPS events. It calculates: how many drivers are in each zone, how many passengers are requesting rides, and what should the surge price be.

Results go to two places:
- DynamoDB — a fast database where the driver app reads the current surge price instantly
- S3 — Amazon's storage where all raw data is saved as files for later analysis

The third layer is the Batch Layer. Once per hour, AWS Glue reads all those S3 files, cleans and aggregates the data, and makes it ready for SQL queries. Amazon Athena then lets us run SQL queries on this data — answering business questions like revenue by city, top drivers, and cancellation trends.

The whole pipeline is managed by AWS Step Functions — like a scheduler that runs everything in the correct order every hour.

For monitoring I have Prometheus collecting metrics and Grafana showing live dashboards. Everything on AWS is created using Terraform — infrastructure as code.

This combination of real-time and batch processing is called the Lambda Architecture — and it is the industry standard pattern for large-scale data systems."

---

## SEGMENT 3 — CODE EXPLANATION
### Time: 5:00 to 9:00

SHOW: File manager or VS Code with src/ folder open

"Let me now explain the important files in this project one by one.

---

SHOW: src/gps_simulator.py

The first file is gps_simulator.py. This is my GPS data generator. It creates virtual drivers — I can choose any number from 500 to 50,000. Each driver runs as a separate thread and sends one GPS event every second to Kafka. The event contains the driver ID, city, latitude, longitude, speed, and a timestamp. This file is what powers all my experiments. I simply change the number of drivers and I get completely different load on the system.

---

SHOW: src/spark_streaming_job.py

The most important file is spark_streaming_job.py. This is the real-time brain of the system.

It reads GPS events from Kafka continuously. Then it does something called a stream-stream join — it matches driver supply events with passenger demand events. If in zone number 5 of Mumbai there are 10 drivers but 20 passengers waiting — demand divided by supply is 2.0 — surge pricing is triggered.

The surge multiplier goes from 1.5 times at mild imbalance up to 3.0 times at extreme imbalance.

Now the most important innovation in my project — the Adaptive Window. This one line of code:

WINDOW_SECONDS = max(2, driver_count divided by 1000)

What this means: at 500 drivers, window is 2 seconds. At 5000 drivers, window is 5 seconds. At 50,000 drivers, window is 10 seconds. The system automatically adjusts how often it processes data based on how busy it is. This single change reduced latency by 49 percent at low driver counts. I measured this in my experiments.

---

SHOW: src/rest_ingestor.py

This file is rest_ingestor.py. It is a FastAPI web server — the HTTP gateway for GPS events. When a driver's phone sends a location update over HTTP, this server receives it and routes it to the correct Kafka topic — critical, surge, or normal — based on the zone's current demand level. This is the production-grade ingestion layer.

---

SHOW: src/schema_evolution.py

This file handles schema evolution. In real systems, the data format changes over time. Version 1 of our GPS event had basic fields. Version 2 added zone ID and additional metadata. This file automatically upgrades old v1 events to v2 format without breaking anything. Old drivers sending v1 events still work. New consumers get the richer v2 data. This is backward compatibility in practice.

---

SHOW: src/data_lineage.py

This file is data_lineage.py. Every time a schema upgrade happens, this file writes an audit record to DynamoDB — what was transformed, when, from which version to which version. This gives us a complete data lineage trail. In real companies this is required for compliance and debugging.

---

SHOW: src/glue_batch_job.py

This is the AWS Glue ETL job. ETL stands for Extract Transform Load. This PySpark script reads raw Parquet files from S3, calculates aggregations like total revenue per city, average earnings per driver, and cancellation rates by surge level, then writes clean data back to S3 in a format that Amazon Athena can query with SQL.

---

SHOW: terraform/ folder

Finally the terraform folder. Every single AWS resource in this project — DynamoDB tables, S3 bucket, IAM roles, Lambda function, Glue job, Athena workgroup, Step Functions, CloudWatch alarms — is defined as code in these files. I can delete everything and recreate the entire AWS infrastructure by running one command: terraform apply. This is Infrastructure as Code — the professional standard for cloud deployments."

---

## SEGMENT 4 — LIVE DEMO
### Time: 9:00 to 14:30

DO: Run `bash scripts/demo.sh` in terminal

---

### STEP 1 — Infrastructure Starting (9:00 to 9:45)

SHOW: Terminal showing docker compose starting

"The script has started. The first thing it does is run Docker Compose — this starts all the services we need locally.

You can see Zookeeper starting — this coordinates the Kafka cluster. Then three Kafka broker containers start — kafka-broker-1, kafka-broker-2, and kafka-broker-3. Having three brokers means if one crashes, the other two still have copies of all messages. No data is lost.

Then Prometheus starts on port 9090 — this collects metrics. And Grafana starts on port 3000 — this shows the live dashboards.

After waiting 35 seconds for everything to be ready, the script creates the three Kafka topics — gps-critical, gps-surge, and gps-normal. You can see the confirmation messages: Topic gps-critical ready, Topic gps-surge ready, Topic gps-normal ready.

The reason I create topics manually is that auto-creation is disabled. In production, you always control exactly which topics exist."

---

### STEP 2 — Grafana Dashboard (9:45 to 10:30)

DO: Press Enter → open browser → go to http://localhost:3000 → login admin/admin

SHOW: Grafana dashboard in browser

"This is Grafana — my real-time monitoring dashboard.

I can see three panels here:

Panel 1 at the top left — Kafka Events Per Second. This shows how many GPS events are flowing through the pipeline every second. Right now it shows zero because no simulation is running yet.

Panel 2 at the top right — Active Surge Zones. This shows how many city zones across our 10 cities are currently in surge pricing mode. Also zero right now.

Panel 3 at the bottom — Batch Processing Latency. This shows how long Spark is taking to process each micro-batch of events in milliseconds. The red dashed line at 5000 milliseconds is our SLA target. We must stay below this line to meet the under-5-second requirement.

These three numbers together tell me everything about the health of the pipeline — throughput, business impact, and processing speed."

DO: Press Enter to start Step 3

---

### STEP 3 — 1000 Driver Simulation (10:30 to 11:45)

SHOW: Terminal showing simulator output + Grafana side by side

"Two things just started.

First — the GPS simulator. You can see the output: Connected to Kafka, then All 10 city simulators running. That means 10 cities each with 100 drivers — total 1000 drivers. Each driver is sending one GPS event per second. The target event rate shows 100 per second.

Second — Spark Structured Streaming has started in the background with WINDOW_SECONDS set to 2. The adaptive window formula gives us: max(2, 1000 divided by 1000) = max(2, 1) = 2 seconds. So Spark processes a fresh batch every 2 seconds.

SHOW: Grafana panels

Now look at Grafana. The Events Per Second panel is climbing — you can see it going up to around 100 events per second. This is exactly what we expected from our experiment result of 105 EPS for this configuration.

The Batch Processing Latency panel is showing values around 3000 to 4000 milliseconds — well below the 5000 millisecond SLA line. The red line is our limit — we are comfortably below it.

The Active Surge Zones panel is showing some zones going into surge — because even with 1000 drivers, certain zones have more passengers than drivers at certain times.

This is real-time surge detection working — 1000 drivers, 100 events per second, latency under 5 seconds."

DO: Press Enter to go to Step 4

---

### STEP 4 — Scaling to 5000 Drivers (11:45 to 12:45)

SHOW: Terminal showing new simulator starting + Grafana

"Now I scale up to 5000 drivers.

The script kills the 1000-driver simulator and starts a new one with 5000 drivers — 500 per city across 10 cities. It also restarts Spark with a new window size.

The adaptive window now calculates: max(2, 5000 divided by 1000) = max(2, 5) = 5 seconds. The window has automatically doubled from 2 to 5 seconds to handle the higher load.

SHOW: Grafana panels

Watch Grafana now. Events Per Second is climbing to around 470. This matches our experiment result of 470 EPS for this configuration.

The Active Surge Zones panel now shows significantly more zones in surge — because with 5000 drivers spread across 10 cities, demand and supply imbalances appear in more zones simultaneously. You can see surge happening in Mumbai, Delhi, Bangalore — multiple cities at the same time.

The latency is around 6000 to 6500 milliseconds — just above our 5-second SLA. This is expected at 5000 drivers with local hardware. In our EC2 experiment the result was similar — 6147 milliseconds. The SLA target requires infrastructure scaling beyond a single laptop."

DO: Press Enter to go to Step 5

---

### STEP 5 — Fault Injection (12:45 to 13:15)

SHOW: Terminal showing fault message + Grafana immediately after

"Now I will demonstrate fault tolerance. The script is injecting a fault — it kills Spark with a hard kill-9 signal. This simulates a real crash — like running out of memory or a hardware failure.

SHOW: Grafana

Look at Grafana immediately. Events Per Second drops to zero. You can see a clear gap — a flat line at the bottom. The system has crashed.

But notice — the GPS simulator is still running. 5000 drivers are still sending events. Those events are going into Kafka and being stored safely on disk. Kafka does not lose them. They are waiting to be processed when the system comes back.

This is the key design decision — Kafka acts as a durable buffer. The data producers do not know or care that processing crashed. They keep going."

DO: Press Enter to go to Step 6

---

### STEP 6 — Recovery (13:15 to 14:00)

SHOW: Terminal showing Spark restarting + Grafana recovering

"Now recovery. The script restarts the exact same Spark job.

When Spark starts, the very first thing it does is read the checkpoint directory — a folder where it saved its progress before crashing. It knows the last Kafka message it successfully processed. It now replays everything from that point forward.

SHOW: Grafana

Watch Grafana — within about 30 seconds the Events Per Second line climbs back up to 470. The gap is filled. All the events that arrived during the crash are now being processed in order.

In our fault experiment we confirmed: recovery time was under 30 seconds on local hardware and under 150 seconds on EC2. And the total number of events processed after recovery matched exactly the total number sent by the GPS simulator. Zero messages lost.

This is production-grade fault tolerance — automatic recovery with zero data loss."

DO: Press Enter to go to Step 7

---

### STEP 7 — Athena Dashboard (14:00 to 14:30)

DO: Browser opens docs/athena_dashboard.html automatically

SHOW: Athena analytics dashboard in browser

"The browser has opened the batch analytics dashboard. This shows real data from Amazon Athena queries run on our AWS infrastructure. Let me now walk through each panel."

DO: Press Enter in terminal (cleanup) — now explain dashboard on screen

---

## SEGMENT 5 — GRAFANA PANELS DETAILED EXPLANATION
### Time: 14:30 to 15:30

SHOW: Grafana dashboard at http://localhost:3000

"Let me explain the Grafana dashboard in more detail.

Panel 1 — Events Per Second.
This panel shows the throughput of the entire pipeline. Every time a GPS event goes from Kafka into Spark and gets processed, it counts here. When you see this number at 100, it means 100 driver GPS locations are being processed every single second. When it jumped to 470, it meant 5000 drivers were active. When it dropped to zero, that was the fault. When it came back to 470, that was the recovery. This one number tells you the heartbeat of the entire system.

Panel 2 — Active Surge Zones.
This panel counts how many geographic zones across all 10 cities are currently showing demand greater than 1.5 times supply. When this number is 0, the city is in balance — fares are normal. When it goes up to 30 or 40, it means 30 or 40 zones across the country are in surge pricing right now. This is the core business metric — the number that drives revenue for the ridesharing company.

Panel 3 — Batch Processing Latency.
This shows how long Spark takes to complete one micro-batch processing cycle in milliseconds. The red dashed line at 5000 milliseconds is the SLA target — the maximum allowed latency. If the line is below red, the system is healthy. If it crosses red, we are breaching the SLA and surge prices are not being updated fast enough.

Prometheus scrapes these metrics from Spark every 15 seconds — that is why the graph updates every 15 seconds. The metric names are spark_kafka_events_per_second, spark_active_surge_zones, and spark_batch_latency_ms."

---

## SEGMENT 6 — ATHENA DASHBOARD PANELS
### Time: 15:30 to 17:00

SHOW: docs/athena_dashboard.html in browser — scroll through each panel

"This dashboard was built using real data from Amazon Athena. Let me explain each panel.

---

Panel 1 — Top Cities by Revenue (Q1)
SHOW: Bar chart — cities on x-axis, revenue in rupees on y-axis

This bar chart shows total revenue in Indian Rupees for each of the 10 cities. Mumbai and Delhi are at the top because they have higher driver and passenger density. The data comes from the city_stats table in our Glue catalogue — it is the result of a real SQL query run on Amazon Athena aggregating 3000 trip records.

---

Panel 2 — Top 10 Driver Earnings (Q2)
SHOW: Table showing driver IDs and earnings

This table shows the top 10 highest-earning drivers in the dataset. Each row shows the driver ID, which city they work in, total earnings in rupees, and total number of trips. The highest-earning drivers are concentrated in Mumbai and Delhi — the high-surge cities. This data comes from the driver_earnings table.

---

Panel 3 — Surge Distribution by City (Q3)
SHOW: Stacked bar chart — cities on x-axis, trip count stacked by surge level

This is a stacked bar chart. For each city, it shows how many trips happened at each surge level — 1.0 times is normal pricing shown in blue, 1.5 times in yellow, 2.0 times in orange, and 2.5 times in red-purple.

You can see that most trips happen at normal pricing — around 40 to 60 percent. But a significant portion happen at 1.5 and 2.0 times surge — and these surge trips generate much higher revenue per trip. Cities like Kolkata and Ahmedabad show more high-surge trips, indicating chronic supply shortages.

---

Panel 4 — Top Zone-Hour Combinations (Q4)
SHOW: Horizontal bar chart or table — zone and hour combinations

This panel shows which zone and hour combinations have the highest trip volume. The pattern is clear — zones near airports, train stations, and commercial areas during morning 8 to 10 AM and evening 6 to 9 PM dominate. These are the commute hours. This tells operations teams exactly where to position drivers to reduce surge and improve completion rates.

---

Panel 5 — Trip Completion Rate by City (Q5)
SHOW: Stacked bar chart — completion percent in green, cancellation in red

This chart shows completion rate versus cancellation rate for each city. Surat and Mumbai have the highest completion rates — around 89 to 90 percent. Kolkata and Ahmedabad have the highest cancellation rates — around 20 to 21 percent.

High cancellation usually means one of two things: either surge prices are too high for that market, or driver supply is too low so passengers cancel before a driver accepts. Operations teams use this chart to decide where to run driver incentive programs.

---

Panel 6 — Surge Impact on Fares and Cancellations (Q6)
SHOW: Dual-axis bar and line chart — surge level on x-axis, fare on left axis, cancellation rate on right axis

This is the most important business insight chart. It has two y-axes.

The blue bars show average fare in rupees — as surge multiplier increases from 1.0 to 2.5, average fare goes from 138 rupees to 314 rupees. Revenue per trip doubles.

The red line shows cancellation rate at each surge level. At 1.0 times — no surge — cancellation rate is 16 percent. At 1.5 times it actually drops to 12 percent — because slightly higher prices reduce casual requests and serious passengers are matched faster. But at 2.5 times surge, cancellation rises to 19 percent as price-sensitive passengers give up.

This tells the pricing algorithm: surge up to 1.5 to 2.0 times is optimal — it increases revenue AND reduces cancellations. Beyond 2.0 times, you are making more per trip but losing customers."

---

## SEGMENT 7 — BENCHMARK GRAPHS
### Time: 17:00 to 19:00

DO: Open experiments/graphs/ folder — show each PNG

"Now let me walk through the 10 benchmark graphs from my experiments.

---

Graph 1 — Throughput Comparison (01_throughput_comparison.png)
SHOW: Bar chart

This bar chart compares Events Per Second across all 8 experiments. The key insight: going from 500 to 1000 drivers almost doubles throughput — from 60 to 105 EPS — because Spark processes batches more efficiently when they are fuller. EC2 and local give almost identical throughput at 5000 drivers — 470 versus 464 — meaning the bottleneck is Spark logic, not hardware. EMR gives only 11 percent more throughput than EC2 at 50,000 drivers but costs 6 times more.

---

Graph 2 — Latency Comparison (02_latency_comparison.png)
SHOW: Bar chart with 3 bars per experiment and red SLA line

This chart shows p50, p95, and p99 latency for each experiment. The red line at 5000 milliseconds is the SLA. Local at 500 and 1000 drivers — all bars below the red line — SLA met. At 5000 drivers the p95 bar just crosses the line — SLA near miss. At 50,000 drivers with EMR, p95 is 132,500 milliseconds — more than 2 minutes. EMR's cluster management overhead makes it unsuitable for our latency-sensitive workload.

---

Graph 3 — Latency Over Time (03_latency_over_time.png)
SHOW: Line chart — time on x-axis, latency on y-axis

This shows latency changing over the duration of each experiment. For healthy experiments like local_1k — the line is stable and flat around 3000 milliseconds. For the fault experiments — you see a sharp spike at the moment of crash, then a return to normal after recovery. For ec2_50k — latency gradually climbs because Kafka lag builds up as the system falls behind.

---

Graph 4 — Throughput Over Time (04_throughput_over_time.png)
SHOW: Line chart — time on x-axis, EPS on y-axis

For stable experiments EPS is a flat line. For the fault experiments — EPS drops to zero at the kill, then recovers sharply. This is the most visually clear proof of fault tolerance. The gap represents the crash. The sharp recovery line represents Kafka replay. Everything resumes exactly.

---

Graph 5 — Cost vs Latency (05_cost_vs_latency.png)
SHOW: Scatter plot — cost on x-axis, latency on y-axis

The ideal position is bottom left — low cost, low latency. Local experiments are at zero cost. EC2 at 5000 drivers — small cost, similar latency to local — good value. EMR at 50,000 — top right corner — highest cost AND highest latency. For our workload, EMR is clearly not the right choice.

---

Graph 6 — Window vs Latency (06_window_vs_latency.png)
SHOW: Bar or line chart — window size vs latency

This directly shows the adaptive window effect. At 2-second window: latency is 3813 milliseconds. At 5-second window: 6147 milliseconds. At 10-second window: 33,374 milliseconds. Smaller window means faster response but more Spark overhead. The adaptive formula automatically picks the best window for each scale.

---

Graph 7 — Scaling Behavior (07_scaling_behavior.png)
SHOW: Dual line chart — drivers on x-axis, EPS and latency on y-axes

EPS grows roughly linearly with driver count — good scalability. But latency grows much faster — this is the fundamental tension in streaming systems. More load means higher throughput but also higher delay. The 5-second SLA line is crossed around 3000 to 4000 drivers on local hardware.

---

Graph 8 — Results Heatmap (08_results_heatmap.png)
SHOW: Color grid — green = good, red = bad

This is a summary of all experiments in one view. Green means good performance — low latency, low cost. Red means bad — high latency, high cost. local_1k is the greenest row — best performance at zero cost. emr_50k is the reddest — worst latency and highest cost. This one chart summarises the entire benchmarking study.

---

Graph 9 — Fault Recovery (09_fault_recovery.png)
SHOW: Timeline chart with red vertical line at fault moment

This focuses on the two fault experiments. The vertical red line is the crash moment. After the crash line, EPS drops to zero. The shaded area is the events buffered in Kafka — not lost, just waiting. After recovery, the line climbs back and all buffered events are processed. Fault_local recovers in 28 seconds. Fault_ec2 recovers in 140 seconds. Both: zero messages lost.

---

Graph 10 — Innovation Impact (10_innovation_impact.png)
SHOW: Bar chart comparing with and without each innovation

This graph quantifies my three key innovations.

Adaptive Window: Without it — latency at 500 drivers would be around 8500 milliseconds. With it — 4328 milliseconds. That is 49 percent improvement.

Three-Tier Topics: Critical events are always processed before normal events — zero critical surge updates delayed by normal GPS traffic.

Conditional Batch Skip: Without skip — Glue runs 24 times per night even when there is no data. With skip — only 3 to 4 runs per night. Savings of approximately 290 rupees per night in idle cloud charges."

---

## SEGMENT 8 — CONCLUSION
### Time: 19:00 to 20:00

SHOW: experiments/results/summary_statistics.csv or results table

"Let me finish with a summary of all 8 experiments.

At 500 drivers with a 2-second window — p95 latency is 4328 milliseconds — SLA met.
At 1000 drivers with a 2-second window — p95 latency is 3813 milliseconds — SLA met — even better than 500 drivers because batches are fuller.
At 5000 drivers — latency goes to 6100 to 6700 milliseconds — just above SLA — acceptable for medium scale.
At 50,000 drivers — latency goes to 33,000 on EC2 and 132,000 on EMR — SLA not met — this requires a larger distributed cluster.

The total cost of running all experiments was approximately 8 to 10 US dollars. Today the system costs only 0.003 dollars per day in storage — because EC2 is stopped and EMR is terminated.

The three most important things I learned from this project:

One — The adaptive window is the single most impactful optimisation. It gave 49 percent latency reduction with zero additional infrastructure cost.

Two — EC2 is more cost-effective than EMR for medium-scale workloads. EMR makes sense only when you need truly massive scale with automatic cluster management — not for our workload size.

Three — Kafka is the foundation of fault tolerance. Without Kafka's durable message storage, a Spark crash would mean lost data. With it, recovery is automatic and complete.

This project demonstrates a real, working, production-grade ridesharing data pipeline — built, tested, and measured on actual AWS infrastructure.

Thank you for watching.

The complete source code is available at:
github.com/amityadav23112000/ridesharing-pipeline"

---

## QUICK REFERENCE — COMMANDS TO RUN DURING DEMO

```bash
# Start demo
cd ~/ridesharing-pipeline
bash scripts/demo.sh

# Check Spark logs in second terminal
tail -f /tmp/spark_demo.log

# Open Grafana
# Browser → http://localhost:3000 → admin / admin

# Open graphs folder
xdg-open experiments/graphs/

# Open Athena dashboard
xdg-open docs/athena_dashboard.html

# Show experiment results in terminal
column -t -s',' experiments/results/summary_statistics.csv
```

---

## TIMING REFERENCE

| Time | What you are saying |
|------|-------------------|
| 0:00 – 2:00 | Introduction and problem statement |
| 2:00 – 5:00 | Architecture explanation |
| 5:00 – 9:00 | Code file explanations |
| 9:00 – 9:45 | Demo Step 1 — infrastructure starting |
| 9:45 – 10:30 | Demo Step 2 — Grafana empty dashboard |
| 10:30 – 11:45 | Demo Step 3 — 1000 drivers + Grafana panels |
| 11:45 – 12:45 | Demo Step 4 — scale to 5000 drivers |
| 12:45 – 13:15 | Demo Step 5 — fault injection |
| 13:15 – 14:00 | Demo Step 6 — recovery |
| 14:00 – 14:30 | Demo Step 7 — open Athena dashboard |
| 14:30 – 15:30 | Grafana panels detailed explanation |
| 15:30 – 17:00 | Athena dashboard 6 panels explanation |
| 17:00 – 19:00 | 10 benchmark graphs explanation |
| 19:00 – 20:00 | Results summary and conclusion |
