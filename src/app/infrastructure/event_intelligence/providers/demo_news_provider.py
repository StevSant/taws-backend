from datetime import UTC, datetime

from app.domain.event_intelligence.entities import NewsEvent
from app.domain.event_intelligence.ports import NewsProviderPort

_DEMO_NEWS: list[NewsEvent] = [
    NewsEvent(
        title="Fed Holds Rates Steady, Signals Cautious Approach",
        description="The Federal Reserve maintained its benchmark interest rate at 5.25-5.50% "
        "and indicated a cautious stance on future cuts.",
        content="The Federal Reserve held interest rates steady at 5.25-5.50% during its latest "
        "meeting, citing persistent inflation concerns. Chair Powell noted that while progress "
        "has been made on inflation, the committee needs more evidence before considering rate "
        "cuts. Markets reacted with mild volatility as traders adjusted their rate-cut "
        "expectations for 2025.",
        source="Demo",
        url="https://example.com/fed-rates",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Tech Sector Surges on AI Earnings Optimism",
        description="Major technology stocks rallied after strong earnings reports from "
        "leading AI companies exceeded analyst expectations.",
        content="The technology sector saw broad gains today as several major companies "
        "reported better-than-expected quarterly earnings, driven by continued growth in "
        "AI-related revenue streams. NVIDIA, Microsoft, and Alphabet all posted gains. "
        "Analysts have revised their price targets upward, citing sustained demand for "
        "AI infrastructure and enterprise adoption.",
        source="Demo",
        url="https://example.com/tech-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Oil Prices Drop Amid Global Demand Concerns",
        description="Crude oil prices fell sharply as new economic data from major "
        "economies suggested slowing demand.",
        content="Oil prices declined over 3% following weaker-than-expected manufacturing "
        "data from China and Europe. Traders are concerned that global economic growth may be "
        "slowing more rapidly than anticipated, reducing near-term demand for crude. OPEC+ has "
        "not signaled any production adjustments at this time.",
        source="Demo",
        url="https://example.com/oil-prices",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Bitcoin Breaks $100K as Institutional Adoption Accelerates",
        description="Bitcoin surged past the $100,000 mark for the first time, driven by "
        "spot ETF inflows and corporate treasury allocations.",
        content="Bitcoin reached a new all-time high above $100,000 as institutional investors "
        "continued to pour capital into spot Bitcoin ETFs. Several publicly traded companies "
        "announced Bitcoin treasury allocations, following MicroStrategy's playbook. Analysts "
        "cite the upcoming halving cycle and favorable regulatory developments as additional "
        "tailwinds for the cryptocurrency market.",
        source="Demo",
        url="https://example.com/bitcoin-100k",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Ethereum Completes Major Network Upgrade, Reducing Gas Fees",
        description="The Ethereum network successfully implemented its latest protocol upgrade, "
        "dramatically reducing transaction costs on layer-1.",
        content="Ethereum's latest network upgrade went live, introducing several EIPs that "
        "optimize gas fee calculations and improve layer-2 interoperability. Early data shows a "
        "40% reduction in average transaction fees for common DeFi operations. The upgrade was "
        "adopted smoothly with broad validator consensus, and the ETH price responded positively.",
        source="Demo",
        url="https://example.com/ethereum-upgrade",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="SEC Approves First Spot Ethereum ETFs",
        description="The SEC granted approval for multiple spot Ethereum ETFs, marking a "
        "milestone for crypto adoption in traditional finance.",
        content="The Securities and Exchange Commission approved applications from several "
        "asset managers to launch spot Ethereum ETFs, following a similar approval for Bitcoin "
        "earlier this year. Industry experts expect billions in inflows over the first year. "
        "ETH rallied 15% on the news as institutional investors now have a regulated vehicle "
        "for direct Ethereum exposure.",
        source="Demo",
        url="https://example.com/eth-etf-approval",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="CPI Report Shows Inflation Cooling Faster Than Expected",
        description="The Consumer Price Index rose 2.8% year-over-year, below the 3.1% "
        "consensus estimate, fueling hopes for earlier rate cuts.",
        content="The Bureau of Labor Statistics reported that headline CPI increased 2.8% "
        "year-over-year, significantly below the 3.1% economists had forecast. Core CPI, "
        "excluding food and energy, came in at 3.0% versus 3.3% expected. Bond yields dropped "
        "sharply as markets priced in a higher probability of a rate cut at the next FOMC "
        "meeting. Equity futures turned positive on the news.",
        source="Demo",
        url="https://example.com/cpi-report",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="NVIDIA Reports Record Quarterly Revenue, Stock Jumps 8%",
        description="NVIDIA smashed earnings estimates with record data-center revenue, "
        "driven by insatiable demand for AI training chips.",
        content="NVIDIA reported quarterly revenue of $35 billion, handily beating the $31 "
        "billion consensus estimate. Data-center revenue alone reached $30 billion, up 154% "
        "year-over-year. The company guided next quarter above expectations, citing continued "
        "supply constraints for its next-generation Blackwell chips. Shares rose 8% in "
        "after-hours trading.",
        source="Demo",
        url="https://example.com/nvidia-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="US Jobs Report Blows Past Expectations, 350K Added",
        description="The US economy added 350,000 jobs in the latest month, far exceeding "
        "the 180,000 consensus estimate and complicating the Fed's rate path.",
        content="The Bureau of Labor Statistics reported that non-farm payrolls increased by "
        "350,000, nearly double the expected 180,000. The unemployment rate held steady at "
        "3.7%, while average hourly earnings rose 0.3% month-over-month. The strong labor "
        "market data reduces the urgency for the Fed to cut rates, sending bond yields higher "
        "and equities lower in early trading.",
        source="Demo",
        url="https://example.com/jobs-report",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="US Imposes New Tariffs on Chinese Imports, Beijing Retaliates",
        description="The US announced 25% tariffs on an additional $50 billion of Chinese "
        "goods, prompting immediate retaliatory measures from China.",
        content="The White House unveiled a new round of tariffs targeting Chinese semiconductors, "
        "electric vehicles, and medical equipment. China responded with tariffs on US agricultural "
        "products and rare earth export restrictions. Global supply chain stocks fell, while "
        "defense and domestic manufacturing names rallied. The WTO warned of potential trade war "
        "escalation affecting global GDP growth.",
        source="Demo",
        url="https://example.com/us-china-tariffs",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Major Bank Settles Regulatory Probe for $2.5 Billion",
        description="A leading global bank agreed to a $2.5 billion settlement with regulators "
        "over inadequate anti-money laundering controls.",
        content="The settlement resolves investigations by the DOJ, Fed, and state regulators "
        "into compliance failures that allowed illicit transactions to flow through the bank's "
        "correspondent banking network. The bank also agreed to enhanced monitoring and an "
        "independent compliance review. Its stock fell 3% on the news, though analysts view "
        "the settlement as removing a key overhang.",
        source="Demo",
        url="https://example.com/bank-settlement",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Pharma Giant Announces Breakthrough in Alzheimer's Treatment",
        description="A phase 3 trial showed a new drug candidate slows cognitive decline by "
        "40%, sending the company's stock up 25%.",
        content="The biotech company reported topline results from its pivotal phase 3 trial, "
        "demonstrating a 40% reduction in cognitive decline measured by the CDR-SB scale over "
        "18 months. The drug targets amyloid-beta plaques with a novel mechanism that shows a "
        "better safety profile than existing treatments. The company plans to file for FDA "
        "approval within the next quarter, and analysts project peak annual sales exceeding "
        "$10 billion.",
        source="Demo",
        url="https://example.com/alzheimers-breakthrough",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="EU Fines Apple $4 Billion Over App Store Practices",
        description="The European Commission levied a record fine against Apple for "
        "anti-competitive App Store policies affecting music streaming services.",
        content="The European Commission fined Apple $4 billion for abusing its dominant "
        "position in the music streaming market through restrictive App Store policies that "
        "prevented developers from informing users of cheaper alternatives outside the iOS "
        "ecosystem. Apple stated it would appeal the decision. The fine represents approximately "
        "1% of Apple's annual revenue and is one of the largest ever imposed by the EU.",
        source="Demo",
        url="https://example.com/apple-eu-fine",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="China GDP Growth Slows to 4.2%, Missing Expectations",
        description="China's economy grew at its slowest pace in decades outside the pandemic "
        "era, as the property crisis and weak consumer demand persist.",
        content="China's GDP expanded 4.2% year-over-year, below the 4.8% forecast and the "
        "government's 5% annual target. Industrial production and retail sales both missed "
        "estimates, signaling deepening economic malaise. The property sector continued to "
        "weigh on growth, with new home prices falling for a 14th consecutive month. The PBOC "
        "is expected to deliver additional stimulus measures in coming weeks.",
        source="Demo",
        url="https://example.com/china-gdp-miss",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Tesla Delivers Record Quarterly Vehicle Numbers, Margins Improve",
        description="Tesla reported record deliveries and improving automotive margins, "
        "beating analyst expectations on both revenue and profit.",
        content="Tesla delivered 484,000 vehicles in the quarter, a new record, driven by "
        "strong demand for the Cybertruck and Model Y. Automotive gross margins excluding "
        "regulatory credits improved to 19.8%, up from 17.5% last quarter, as cost reduction "
        "initiatives and higher-margin Cybertruck sales boosted profitability. Energy storage "
        "deployments also hit a record, with Megapack revenue doubling year-over-year.",
        source="Demo",
        url="https://example.com/tesla-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="OPEC+ Surprises Markets with Deep Production Cut",
        description="OPEC+ announced an unexpected 1.5 million barrel per day production cut, "
        "sending oil prices sharply higher.",
        content="OPEC+ ministers agreed to a surprise 1.5 million bpd production cut, citing "
        "weaker demand forecasts and a desire to stabilize prices. Brent crude jumped 6% to "
        "$92 per barrel immediately following the announcement. The cut is expected to keep "
        "global oil markets in deficit through the second half of the year, raising concerns "
        "about inflationary pressures on transportation and manufacturing costs.",
        source="Demo",
        url="https://example.com/opec-cut",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Japan's Nikkei Hits All-Time High on Corporate Governance Reforms",
        description="Japan's benchmark index surpassed its 1989 record as foreign investors "
        "flooded into Tokyo-listed stocks amid governance improvements.",
        content="The Nikkei 225 closed at a new all-time high, surpassing the previous record "
        "set in 1989. The rally has been fueled by Tokyo Stock Exchange corporate governance "
        "reforms, record share buybacks, and a weak yen boosting exporter earnings. Foreign "
        "investors have poured over $60 billion into Japanese equities this year, making it "
        "one of the best-performing major markets globally.",
        source="Demo",
        url="https://example.com/nikkei-record",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Gold Surges to $2,500 as Central Banks Increase Reserves",
        description="Gold prices hit a new all-time high above $2,500 per ounce, driven by "
        "central bank buying and geopolitical uncertainty.",
        content="Gold breached the $2,500 level for the first time as central banks, particularly "
        "those in China, India, and Turkey, continued diversifying reserves away from the US "
        "dollar. Global central bank gold purchases reached 1,000 tonnes in the first half of "
        "the year. The rally was further supported by escalating tensions in the Middle East "
        "and Eastern Europe, driving safe-haven demand.",
        source="Demo",
        url="https://example.com/gold-ath",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Amazon Acquires AI Startup for $8 Billion in Talent Grab",
        description="Amazon announced its largest AI acquisition to date, purchasing a "
        "leading foundation-model startup for $8 billion in cash.",
        content="Amazon's acquisition of the AI startup gives it access to cutting-edge large "
        "language model technology and a team of over 200 AI researchers. The deal is seen as "
        "Amazon's bid to close the gap with Microsoft and Google in the enterprise AI market. "
        "AWS plans to integrate the startup's models into its Bedrock platform, offering "
        "customers an additional foundation model option with competitive pricing.",
        source="Demo",
        url="https://example.com/amazon-ai-acquisition",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Global Semiconductor Shortage Eases as New Fabs Come Online",
        description="Chip supply constraints are finally easing as new fabrication plants "
        "in the US, Europe, and Asia begin volume production.",
        content="The global semiconductor shortage that has plagued industries since 2020 is "
        "showing significant signs of abating. TSMC's new Arizona fab, Samsung's Texas expansion, "
        "and Intel's European facilities have all begun volume shipments. Lead times for "
        "non-leading-edge chips have dropped to 12 weeks from a peak of 26 weeks. Auto "
        "manufacturers expect production to normalize by next quarter, though advanced AI chips "
        "remain in tight supply.",
        source="Demo",
        url="https://example.com/chip-shortage-eases",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="European Natural Gas Prices Spike 20% on Supply Disruption",
        description="Natural gas prices surged after an unexpected outage at a major Norwegian "
        "gas facility threatened winter supply.",
        content="European natural gas futures jumped 20% following an unplanned outage at "
        "Norway's Hammerfest LNG plant, one of Europe's largest export facilities. The outage "
        "comes as the region enters peak winter heating season with already-depleted storage "
        "levels. EU energy ministers called an emergency meeting to discuss contingency measures, "
        "including potential demand reduction targets and accelerated LNG imports from Qatar.",
        source="Demo",
        url="https://example.com/gas-price-surge",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="S&P 500 Enters Correction Territory Amid Growth Fears",
        description="The broad market index fell 10% from its recent high as a confluence "
        "of weak economic data and earnings warnings rattled investors.",
        content="The S&P 500 officially entered a correction, falling 10% from its all-time "
        "high set three months ago. The sell-off accelerated after a string of disappointing "
        "earnings from consumer-facing companies and weaker-than-expected retail sales data. "
        "The VIX volatility index spiked above 30, its highest level in 18 months. Defensive "
        "sectors like utilities and healthcare outperformed, while technology and consumer "
        "discretionary led the decline.",
        source="Demo",
        url="https://example.com/sp500-correction",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Russia-Ukraine Peace Talks Collapse, Energy Markets React",
        description="Peace negotiations between Russia and Ukraine broke down, sending "
        "European natural gas and wheat futures sharply higher.",
        content="Diplomatic efforts to end the conflict collapsed after both sides failed to "
        "agree on territorial terms. European natural gas prices jumped 15% on concerns about "
        "remaining transit routes through Ukraine. Wheat futures rose 8% as the Black Sea grain "
        "corridor remains uncertain. Defense stocks across NATO members rallied, while European "
        "airlines and tourism stocks declined on renewed travel disruption fears.",
        source="Demo",
        url="https://example.com/geopolitics-escalation",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Retail Giant Warns of Weak Holiday Season, Shares Plunge 12%",
        description="A major US retailer cut its full-year guidance, citing cautious consumer "
        "spending and rising inventory costs ahead of the holiday season.",
        content="The retailer reported quarterly same-store sales growth of just 0.5%, well "
        "below the 2.5% consensus, and lowered its Q4 guidance citing 'increasingly cautious "
        "consumer behavior.' Management pointed to depleted pandemic savings, resuming student "
        "loan payments, and persistent inflation as headwinds. The warning dragged down the "
        "entire retail sector, with consumer discretionary ETFs falling 3% on the day.",
        source="Demo",
        url="https://example.com/retail-warning",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Cyberattack Disrupts Major US Pipeline Operations",
        description="A ransomware attack forced a major US fuel pipeline operator to halt "
        "operations, sending gasoline futures up 8%.",
        content="The pipeline operator, responsible for transporting approximately 45% of the "
        "East Coast's fuel supply, shut down its systems after a ransomware attack. The company "
        "stated it is working with federal law enforcement and cybersecurity firms to restore "
        "operations. Gasoline futures jumped 8% on supply disruption fears, and the White House "
        "issued an emergency waiver to allow truck transport of fuel. Energy infrastructure "
        "cybersecurity stocks rallied on the news.",
        source="Demo",
        url="https://example.com/pipeline-cyberattack",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="FedEx Cuts Forecast as Global Trade Volumes Decline",
        description="FedEx withdrew its full-year guidance after a sharp drop in package "
        "volumes, citing weakening global trade and industrial activity.",
        content="FedEx reported a 12% decline in express package volumes and cut its fiscal "
        "year forecast, triggering a 15% drop in its share price. The company cited softening "
        "global trade, particularly in Asia-Europe routes, and a shift toward slower, cheaper "
        "shipping options by cost-conscious consumers. The warning is widely viewed as a "
        "bellwether for global economic health, with analysts flagging recession risks.",
        source="Demo",
        url="https://example.com/fedex-warning",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Housing Market Cools as Mortgage Rates Hit 7.5%",
        description="US home sales fell for the fifth consecutive month as mortgage rates "
        "climbed to their highest level in over two decades.",
        content="Existing home sales dropped 4.5% month-over-month, with the median home price "
        "declining slightly for the first time in 18 months. The average 30-year fixed mortgage "
        "rate reached 7.5%, its highest since 2000, pricing out a significant portion of "
        "potential buyers. Homebuilder stocks fell sharply, while rental REITs gained as "
        "prospective buyers remained in the rental market. Housing inventory is beginning to "
        "build, offering some relief to prospective buyers.",
        source="Demo",
        url="https://example.com/housing-market",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="SpaceX Valuation Tops $350 Billion After Secondary Share Sale",
        description="SpaceX's valuation surged past $350 billion following a secondary share "
        "sale, making it the world's most valuable private company.",
        content="SpaceX completed a secondary share sale that valued the company at $350 "
        "billion, up from $210 billion in the previous round. The valuation reflects growing "
        "revenue from the Starlink satellite internet business, which recently surpassed 3 "
        "million subscribers, and optimism about the Starship program's progress. Existing "
        "investors including a16z and Fidelity participated in the tender offer, with new "
        "investors from the Middle East also joining.",
        source="Demo",
        url="https://example.com/spacex-valuation",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Global Cyberattack Targets Financial Institutions, Central Banks on Alert",
        description="A sophisticated ransomware campaign hit multiple banks across Europe and "
        "Asia, disrupting payment systems and ATM networks.",
        content="A coordinated cyberattack attributed to a state-backed group targeted at least "
        "a dozen financial institutions across Europe and Asia. Several banks reported "
        "intermittent outages in their online banking platforms and ATM networks. Central banks "
        "issued emergency alerts and activated cyber-response protocols. The attack exploited a "
        "zero-day vulnerability in widely-used banking software. Cybersecurity stocks surged, "
        "while affected bank shares declined amid concerns about liability and remediation costs.",
        source="Demo",
        url="https://example.com/financial-cyberattack",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Disney+ Subscribers Surpass Netflix in Streaming Wars Milestone",
        description="Disney's streaming service overtook Netflix in global subscribers for "
        "the first time, driven by international expansion and sports content.",
        content="Disney+ reported 280 million global subscribers, edging past Netflix's 275 "
        "million. The growth was fueled by the Disney-Hulu bundle in international markets and "
        "exclusive sports rights including UEFA Champions League and NFL Sunday Ticket. Disney's "
        "streaming division turned its first quarterly profit, validating the company's "
        "direct-to-consumer strategy. Netflix shares fell 5% on the news despite reporting "
        "strong subscriber growth in its own quarter.",
        source="Demo",
        url="https://example.com/disney-streaming",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Hurricane Disrupts Gulf Coast Refineries, Gasoline Prices Spike",
        description="A major hurricane forced the shutdown of multiple refineries along the "
        "Gulf Coast, disrupting nearly 20% of US fuel production capacity.",
        content="A Category 4 hurricane made landfall along the Louisiana coast, forcing the "
        "evacuation and shutdown of six refineries representing approximately 3.5 million "
        "barrels per day of capacity. Gasoline futures surged 12% on supply concerns, and the "
        "DOE announced it would make Strategic Petroleum Reserve releases available to affected "
        "refineries. Insured loss estimates range from $15-25 billion, making it one of the "
        "costliest hurricanes in US history. Energy infrastructure and construction stocks "
        "moved higher on rebuilding expectations.",
        source="Demo",
        url="https://example.com/hurricane-refineries",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Walmart Reports Strong Earnings as Value-Conscious Shoppers Flock",
        description="Walmart beat earnings estimates as higher-income households increasingly "
        "shifted spending to the discount retailer amid persistent inflation.",
        content="Walmart reported same-store sales growth of 4.8%, beating the 3.2% consensus, "
        "with particular strength in grocery and general merchandise. The company noted that "
        "households earning over $100,000 now represent its fastest-growing customer segment. "
        "E-commerce sales grew 22% year-over-year, driven by pickup and delivery services. "
        "Walmart raised its full-year guidance, contrasting sharply with warnings from other "
        "retailers and reinforcing its position as a defensive holding.",
        source="Demo",
        url="https://example.com/walmart-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Bank of Japan Ends Negative Interest Rate Policy",
        description="The Bank of Japan raised its benchmark rate above zero for the first "
        "time in 17 years, marking a historic shift in monetary policy.",
        content="The Bank of Japan raised its policy rate from -0.1% to 0.25%, ending the "
        "world's last negative interest rate regime. The move triggered a sharp appreciation "
        "of the yen, which gained 3% against the dollar. Japanese government bond yields rose, "
        "and the Nikkei initially fell before recovering. The BOJ signaled further gradual "
        "normalization if inflation remains sustainably above 2%, marking a major shift from "
        "decades of ultra-loose monetary policy.",
        source="Demo",
        url="https://example.com/boj-rate-hike",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Pfizer and BioNTech Launch New mRNA Vaccine Targeting Multiple Cancers",
        description="The companies announced positive phase 2 results for a personalized mRNA "
        "cancer vaccine, with plans to fast-track to phase 3 trials.",
        content="Pfizer and BioNTech reported that their personalized mRNA cancer vaccine, "
        "combined with an immune checkpoint inhibitor, reduced the risk of relapse by 45% in "
        "patients with resected melanoma. The vaccine is tailored to each patient's tumor "
        "mutations and can be manufactured in under six weeks. The companies plan to initiate "
        "phase 3 trials across multiple cancer types, including lung and pancreatic cancer, "
        "by the end of the year.",
        source="Demo",
        url="https://example.com/mrna-cancer-vaccine",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Saudi Arabia Unveils $500 Billion 'NEOM' Phase 2 Investment Plan",
        description="Saudi Arabia announced the second phase of its NEOM megacity project, "
        "with a focus on renewable energy, hydrogen production, and tech infrastructure.",
        content="The Saudi sovereign wealth fund committed an additional $500 billion to the "
        "NEOM project's second phase, which includes the world's largest green hydrogen plant, "
        "a next-generation semiconductor fabrication cluster, and a floating port city. The "
        "announcement is part of Vision 2030's push to diversify the Saudi economy away from "
        "oil. International construction and engineering firms saw their stocks rise on the "
        "news, while renewable energy companies anticipate major equipment supply contracts.",
        source="Demo",
        url="https://example.com/neom-phase2",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="FDA Approves First Gene Therapy for Sickle Cell Disease",
        description="The FDA approved a groundbreaking CRISPR-based gene therapy for sickle "
        "cell disease, offering a potential cure for the genetic disorder.",
        content="The FDA approved Casgevy, a CRISPR-based gene therapy developed by Vertex "
        "and CRISPR Therapeutics, for the treatment of sickle cell disease. The one-time "
        "treatment, priced at $2.2 million per patient, has shown a 95% rate of eliminating "
        "vaso-occlusive crises in clinical trials. Insurance coverage discussions are underway, "
        "with CMS indicating it will cover the therapy for eligible Medicare patients. The "
        "approval marks a milestone for gene editing technology and opens the door for similar "
        "treatments for other genetic disorders.",
        source="Demo",
        url="https://example.com/gene-therapy-approval",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="UK Inflation Drops Below 2% Target for First Time in Three Years",
        description="UK CPI fell to 1.8%, below the Bank of England's 2% target, "
        "strengthening the case for accelerated rate cuts.",
        content="UK headline inflation fell to 1.8%, its lowest level in over three years and "
        "below the Bank of England's 2% target for the first time since 2021. Core inflation "
        "also moderated to 2.3%, down from 2.8%. The pound weakened against the dollar and "
        "euro as markets priced in a higher probability of a rate cut at the next BOE meeting. "
        "UK gilt yields fell, and the FTSE 100 rallied on the prospect of cheaper borrowing "
        "costs boosting economic activity.",
        source="Demo",
        url="https://example.com/uk-inflation",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Microsoft Announces $80 Billion Cloud Infrastructure Expansion",
        description="Microsoft unveiled plans to invest $80 billion in global data-center "
        "capacity over the next fiscal year to meet surging AI demand.",
        content="Microsoft's capital expenditure plan, the largest in its history, will fund "
        "new data-center regions in the US, Europe, Asia, and South America. The investment is "
        "driven by capacity constraints in Azure AI services, which have seen demand outstrip "
        "supply for several quarters. Microsoft also announced partnerships with renewable "
        "energy providers to power the new data centers with carbon-free energy. The spending "
        "plan is expected to benefit infrastructure suppliers and construction firms.",
        source="Demo",
        url="https://example.com/microsoft-cloud-spend",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Warren Buffett's Berkshire Hathaway Builds $200 Billion Cash Pile",
        description="Berkshire Hathaway's cash reserves swelled to a record $200 billion as "
        "Buffett struggles to find attractive acquisition targets at current valuations.",
        content="Berkshire Hathaway's cash and Treasury bill holdings reached an unprecedented "
        "$200 billion, representing nearly 30% of the conglomerate's market capitalization. "
        "The company sold significant equity positions during the quarter, including further "
        "reductions in its Apple stake. Buffett's growing cash pile is widely interpreted as a "
        "signal that he views the broader market as overvalued. The annual Berkshire shareholder "
        "meeting is expected to focus on capital allocation strategy and succession planning.",
        source="Demo",
        url="https://example.com/berkshire-cash",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="EU Passes Landmark AI Regulation Act, First of Its Kind Globally",
        description="The European Union approved comprehensive AI regulations, imposing strict "
        "requirements on high-risk AI systems and generative models.",
        content="The EU AI Act was formally adopted, establishing a risk-based regulatory "
        "framework for artificial intelligence. High-risk AI applications in healthcare, "
        "finance, and law enforcement face stringent testing, transparency, and human-oversight "
        "requirements. Generative AI models must disclose training data sources and implement "
        "safeguards against harmful content. Non-compliance penalties reach up to 7% of global "
        "annual revenue. Tech companies are racing to comply before the phased implementation "
        "deadlines begin in 12 months.",
        source="Demo",
        url="https://example.com/eu-ai-act",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Major Port Strike Threatens US Supply Chain Ahead of Holiday Season",
        description="Dockworkers at East Coast and Gulf Coast ports voted to authorize a "
        "strike, threatening billions in holiday merchandise shipments.",
        content="The International Longshoremen's Association voted overwhelmingly to authorize "
        "a strike at 36 ports from Maine to Texas, citing stalled contract negotiations over "
        "automation and wage increases. A strike would affect ports handling approximately 60% "
        "of US container traffic. Retailers are racing to accelerate shipments and reroute "
        "cargo to West Coast ports. The White House urged both sides to reach an agreement, "
        "noting the potential economic impact during the peak holiday shipping season.",
        source="Demo",
        url="https://example.com/port-strike",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="JPMorgan Reports Record Annual Profit, Investment Banking Rebounds",
        description="JPMorgan Chase posted record annual earnings as investment banking fees "
        "surged 35% and net interest income remained elevated.",
        content="JPMorgan reported full-year net income of $62 billion, a record for any US "
        "bank. Investment banking fees rebounded strongly, up 35% year-over-year, driven by a "
        "resurgence in M&A advisory and equity underwriting. Net interest income remained "
        "elevated at $95 billion as the bank benefited from higher-for-longer interest rates. "
        "CEO Jamie Dimon cautioned about geopolitical risks and persistent inflationary "
        "pressures but noted that the US consumer remains resilient.",
        source="Demo",
        url="https://example.com/jpmorgan-earnings",
        published_at=datetime.now(UTC),
    ),
    NewsEvent(
        title="Drought Threatens Panama Canal Operations, Shipping Costs Soar",
        description="Historic low water levels in the Panama Canal forced further restrictions "
        "on vessel traffic, disrupting global trade routes.",
        content="The Panama Canal Authority announced additional draft restrictions and reduced "
        "daily transit slots as a severe drought continued to affect Gatun Lake water levels. "
        "Container ships are being forced to lighten loads or take longer alternative routes "
        "around South America. Shipping costs for Asia-to-US East Coast routes have doubled "
        "as capacity tightens. The disruption is expected to persist until the rainy season "
        "begins, with potential knock-on effects on holiday inventory and consumer prices.",
        source="Demo",
        url="https://example.com/panama-canal-drought",
        published_at=datetime.now(UTC),
    ),
]


class DemoNewsProvider(NewsProviderPort):
    """Returns a small set of hardcoded demo news events for testing the pipeline.

    Useful for development and demonstration without needing a real news API key.
    """

    async def fetch_latest_news(self) -> list[NewsEvent]:
        return list(_DEMO_NEWS)