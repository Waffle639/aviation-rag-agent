-- Aviation golden dataset v1.
-- This seed is intentionally separate from the production corpus tables.
-- Cases are proposed until reviewed and promoted to approved.

insert into evaluation.datasets (
    dataset_id, name, version, corpus_manifest_sha256, status, metadata
)
values (
    'aviation_golden_v1',
    'aviation_golden',
    'v1',
    '7e11f5a7be737823675d5d6dd7a024eb4c5e775694e141c4a2e7393e9d09dd15',
    'draft',
    '{"language":"en","case_count":36,"evidence_locator":"source_file_and_lines"}'::jsonb
)
on conflict (dataset_id) do nothing;

insert into evaluation.cases (
    case_id, dataset_id, question, reference_answer, answerable,
    expected_abstention, aircraft, variant, category, difficulty,
    split, expected_facts, expected_numbers, tags, status
)
values
(
    'av_0001', 'aviation_golden_v1',
    'When was the A320 programme launched, and when did the aircraft first fly?',
    'The programme was launched in March 1984, and the A320 first flew on 22 February 1987.',
    true, false, 'Airbus A320 family', 'A320', 'date', 'easy', 'development',
    '["programme launched in March 1984", "first flight on 22 February 1987"]'::jsonb,
    '[]'::jsonb, '["single-hop", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0002', 'aviation_golden_v1',
    'Which variants followed the original A320 in the A320 family?',
    'The A321, A319, and A318 followed the original A320.',
    true, false, 'Airbus A320 family', 'A318/A319/A321', 'variant', 'easy', 'development',
    '["A321 followed first", "A319 followed", "A318 was the shortest variant"]'::jsonb,
    '[]'::jsonb, '["list", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0003', 'aviation_golden_v1',
    'Which engine options are listed for the A320 family, and what exceptions are given for the A318?',
    'The family used CFM56-5A or -5B and IAE V2500 engines. The A318 used CFM56-5B or PW6000 engines instead of the IAE V2500.',
    true, false, 'Airbus A320 family', 'A318', 'engines', 'medium', 'development',
    '["CFM56-5A", "CFM56-5B", "IAE V2500", "PW6000 for A318"]'::jsonb,
    '[]'::jsonb, '["multi-fact", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0004', 'aviation_golden_v1',
    'What flight-control technologies did the A320 family pioneer in airliners?',
    'It pioneered digital fly-by-wire and side-stick flight controls.',
    true, false, 'Airbus A320 family', 'family', 'systems', 'easy', 'development',
    '["digital fly-by-wire", "side-stick flight controls"]'::jsonb,
    '[]'::jsonb, '["definition", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0005', 'aviation_golden_v1',
    'What maximum take-off weight range and range are given for A320 family variants?',
    'The variants have maximum take-off weights from 68 to 93.5 tonnes and ranges from 5,740 to 6,940 kilometres.',
    true, false, 'Airbus A320 family', 'family', 'numeric', 'medium', 'development',
    '["maximum take-off weight range", "range"]'::jsonb,
    '[{"name":"mtow_min","value":68,"unit":"tonnes"},{"name":"mtow_max","value":93.5,"unit":"tonnes"},{"name":"range_min","value":5740,"unit":"km"},{"name":"range_max","value":6940,"unit":"km"}]'::jsonb,
    '["numeric", "range", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0006', 'aviation_golden_v1',
    'How long is the A318 and how many passengers does it typically accommodate?',
    'The A318 is 31.4 metres long and typically accommodates 107 to 132 passengers.',
    true, false, 'Airbus A320 family', 'A318', 'numeric', 'easy', 'development',
    '["A318 length", "A318 passenger capacity"]'::jsonb,
    '[{"name":"length","value":31.4,"unit":"m"},{"name":"passengers_min","value":107,"unit":"passengers"},{"name":"passengers_max","value":132,"unit":"passengers"}]'::jsonb,
    '["numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0007', 'aviation_golden_v1',
    'What are the length and passenger capacity of the A320?',
    'The A320 is 37.6 metres long and can accommodate 150 to 186 passengers.',
    true, false, 'Airbus A320 family', 'A320', 'numeric', 'easy', 'development',
    '["A320 length", "A320 passenger capacity"]'::jsonb,
    '[{"name":"length","value":37.6,"unit":"m"},{"name":"passengers_min","value":150,"unit":"passengers"},{"name":"passengers_max","value":186,"unit":"passengers"}]'::jsonb,
    '["numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0008', 'aviation_golden_v1',
    'How does the A321 compare with the A320 in length and seating capacity?',
    'The A321 is longer and carries more passengers: it is 44.5 metres long with 185 to 230 seats, while the A320 is 37.6 metres long with 150 to 186 passengers.',
    true, false, 'Airbus A320 family', 'A320/A321', 'comparison', 'medium', 'development',
    '["A321 is longer", "A321 has higher seating range"]'::jsonb,
    '[{"name":"a321_length","value":44.5,"unit":"m"},{"name":"a320_length","value":37.6,"unit":"m"}]'::jsonb,
    '["comparison", "numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0009', 'aviation_golden_v1',
    'What fuel-economy improvement is claimed for the A320neo?',
    'The A320neo offers up to 15% better fuel economy.',
    true, false, 'Airbus A320 family', 'A320neo', 'numeric', 'easy', 'development',
    '["A320neo fuel economy improvement"]'::jsonb,
    '[{"name":"fuel_economy_improvement","value":15,"unit":"percent"}]'::jsonb,
    '["numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0010', 'aviation_golden_v1',
    'What is the A321-100 maximum takeoff weight stated in the source?',
    'The A321-100 maximum takeoff weight is 83,000 kg (183,000 lb).',
    true, false, 'Airbus A320 family', 'A321-100', 'numeric', 'medium', 'development',
    '["A321-100 maximum takeoff weight"]'::jsonb,
    '[{"name":"mtow","value":83000,"unit":"kg"},{"name":"mtow_imperial","value":183000,"unit":"lb"}]'::jsonb,
    '["numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0011', 'aviation_golden_v1',
    'When did the A330-300 first fly and enter service?',
    'The A330-300 first flew in November 1992 and entered service with Air Inter in January 1994.',
    true, false, 'Airbus A330', 'A330-300', 'date', 'easy', 'development',
    '["A330-300 maiden flight November 1992", "A330-300 entered service January 1994"]'::jsonb,
    '[]'::jsonb, '["date", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0012', 'aviation_golden_v1',
    'Which three engine manufacturers or engine families are listed for the A330?',
    'The A330 is listed with General Electric CF6, Pratt & Whitney PW4000, and Rolls-Royce Trent 700 engines.',
    true, false, 'Airbus A330', 'family', 'engines', 'easy', 'development',
    '["General Electric CF6", "Pratt & Whitney PW4000", "Rolls-Royce Trent 700"]'::jsonb,
    '[]'::jsonb, '["list", "engines", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0013', 'aviation_golden_v1',
    'How do the A330-300 and A330-200 compare in the stated range and passenger figures?',
    'The A330-300 has a range of 11,750 km with 277 passengers, while the A330-200 can cover 13,450 km with 247 passengers.',
    true, false, 'Airbus A330', 'A330-200/A330-300', 'comparison', 'medium', 'development',
    '["A330-300 range and passengers", "A330-200 range and passengers"]'::jsonb,
    '[{"name":"a330_300_range","value":11750,"unit":"km"},{"name":"a330_200_range","value":13450,"unit":"km"},{"name":"a330_300_passengers","value":277,"unit":"passengers"},{"name":"a330_200_passengers","value":247,"unit":"passengers"}]'::jsonb,
    '["comparison", "numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0014', 'aviation_golden_v1',
    'Which variants make up the A330neo?',
    'The A330neo comprises the A330-800 and A330-900.',
    true, false, 'Airbus A330', 'A330neo', 'variant', 'easy', 'development',
    '["A330-800", "A330-900"]'::jsonb,
    '[]'::jsonb, '["list", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0015', 'aviation_golden_v1',
    'What maximum takeoff weight did the A330 have in 2015 according to the source?',
    'The A330 maximum takeoff weight had grown to 242 tonnes in 2015.',
    true, false, 'Airbus A330', 'family', 'numeric', 'medium', 'development',
    '["A330 MTOW in 2015"]'::jsonb,
    '[{"name":"mtow","value":242,"unit":"tonnes"}]'::jsonb,
    '["numeric", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0016', 'aviation_golden_v1',
    'What payload and range combinations are given for the A330-200F?',
    'The A330-200F can carry 65 tonnes over 7,400 km or 70 tonnes up to 5,900 km.',
    true, false, 'Airbus A330', 'A330-200F', 'numeric', 'medium', 'development',
    '["65 tonnes over 7400 km", "70 tonnes over 5900 km"]'::jsonb,
    '[{"name":"payload_1","value":65,"unit":"tonnes"},{"name":"range_1","value":7400,"unit":"km"},{"name":"payload_2","value":70,"unit":"tonnes"},{"name":"range_2","value":5900,"unit":"km"}]'::jsonb,
    '["numeric", "freighter", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0017', 'aviation_golden_v1',
    'When did the Boeing 747 first fly and enter service?',
    'The first 747 flight took place on February 9, 1969, and it entered service with Pan Am on January 22, 1970.',
    true, false, 'Boeing 747', 'family', 'date', 'easy', 'development',
    '["first flight February 9 1969", "entered service January 22 1970"]'::jsonb,
    '[]'::jsonb, '["date", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0018', 'aviation_golden_v1',
    'What cruise speed and typical three-class passenger capacity are stated for the Boeing 747?',
    'The Boeing 747 has a Mach 0.85 cruise speed and typically accommodates 366 passengers in three travel classes.',
    true, false, 'Boeing 747', 'family', 'numeric', 'medium', 'development',
    '["Mach 0.85 cruise speed", "366 passengers in three classes"]'::jsonb,
    '[{"name":"cruise_speed","value":0.85,"unit":"Mach"},{"name":"passengers","value":366,"unit":"passengers"}]'::jsonb,
    '["numeric", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0019', 'aviation_golden_v1',
    'Which engine is associated with the Boeing 747-8 in the source?',
    'The Boeing 747-8 is powered by a General Electric GEnx turbofan engine, a version developed from the 787 Dreamliner engine.',
    true, false, 'Boeing 747', '747-8', 'engines', 'easy', 'development',
    '["General Electric GEnx turbofan", "technology from 787"]'::jsonb,
    '[]'::jsonb, '["engine", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0020', 'aviation_golden_v1',
    'What are the length and maximum takeoff weight of the Boeing 747-8?',
    'The Boeing 747-8 is 250 feet (76 m) long and has a maximum takeoff weight of 975,000 pounds (442 t).',
    true, false, 'Boeing 747', '747-8', 'numeric', 'easy', 'development',
    '["747-8 length", "747-8 MTOW"]'::jsonb,
    '[{"name":"length","value":250,"unit":"ft"},{"name":"mtow","value":975000,"unit":"lb"}]'::jsonb,
    '["numeric", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0021', 'aviation_golden_v1',
    'What payload and range are stated for the Boeing 747-8 freighter?',
    'The freighter can haul 308,000 pounds (140 t) over 4,120 nautical miles.',
    true, false, 'Boeing 747', '747-8F', 'numeric', 'easy', 'development',
    '["747-8F payload and range"]'::jsonb,
    '[{"name":"payload","value":308000,"unit":"lb"},{"name":"range","value":4120,"unit":"nmi"}]'::jsonb,
    '["numeric", "freighter", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0022', 'aviation_golden_v1',
    'How many passengers and what range are stated for the Boeing 747-8 Intercontinental?',
    'The Intercontinental can carry 467 passengers in a typical three-class configuration and has a range of 7,790 nautical miles.',
    true, false, 'Boeing 747', '747-8I', 'numeric', 'easy', 'development',
    '["747-8I passengers and range"]'::jsonb,
    '[{"name":"passengers","value":467,"unit":"passengers"},{"name":"range","value":7790,"unit":"nmi"}]'::jsonb,
    '["numeric", "passenger", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0023', 'aviation_golden_v1',
    'What was the maiden flight date and service entry date of the Chengdu J-20?',
    'The J-20 made its maiden flight on 11 January 2011 and entered service in March 2017.',
    true, false, 'Chengdu J-20', 'base model', 'date', 'easy', 'development',
    '["J-20 maiden flight 11 January 2011", "J-20 entered service March 2017"]'::jsonb,
    '[]'::jsonb, '["date", "military", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0024', 'aviation_golden_v1',
    'What are the three notable J-20 variants described in the source?',
    'They are the initial production model, a revised airframe variant with new engines and thrust-vectoring control, and an aircraft-teaming-capable twin-seat variant.',
    true, false, 'Chengdu J-20', 'family', 'variant', 'medium', 'development',
    '["initial production model", "revised airframe with new engines and thrust-vectoring", "twin-seat variant"]'::jsonb,
    '[]'::jsonb, '["list", "military", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0025', 'aviation_golden_v1',
    'What design features of the F-16 are listed as key features?',
    'The source lists a frameless bubble canopy, side-stick control, a seat reclined 30 degrees, and relaxed static stability with fly-by-wire controls.',
    true, false, 'General Dynamics F-16', 'family', 'systems', 'medium', 'development',
    '["frameless bubble canopy", "side-stick", "30 degree reclined seat", "relaxed static stability/fly-by-wire"]'::jsonb,
    '[{"name":"seat_recline","value":30,"unit":"degrees"}]'::jsonb,
    '["multi-fact", "military", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0026', 'aviation_golden_v1',
    'What are the three main variants of the F-35?',
    'The three main variants are the F-35A conventional takeoff and landing variant, the F-35B short-takeoff and vertical-landing variant, and the F-35C catapult-assisted takeoff and arrested-recovery variant.',
    true, false, 'Lockheed Martin F-35', 'F-35A/F-35B/F-35C', 'variant', 'easy', 'development',
    '["F-35A CTOL", "F-35B STOVL", "F-35C carrier variant"]'::jsonb,
    '[]'::jsonb, '["list", "military", "variant", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0027', 'aviation_golden_v1',
    'When did the F-22 first fly and formally enter service?',
    'The F-22 first flew in 1997 and formally entered service in December 2005 as the F-22A.',
    true, false, 'Lockheed Martin F-22', 'F-22A', 'date', 'easy', 'development',
    '["F-22 first flew in 1997", "entered service December 2005"]'::jsonb,
    '[]'::jsonb, '["date", "military", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0028', 'aviation_golden_v1',
    'What was the original intended role of the Eurofighter Typhoon?',
    'It was originally designed as an air-superiority fighter.',
    true, false, 'Eurofighter Typhoon', 'family', 'role', 'easy', 'development',
    '["original air-superiority role"]'::jsonb,
    '[]'::jsonb, '["definition", "military", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0029', 'aviation_golden_v1',
    'What type of aircraft is the Su-47 and was it put into serial production?',
    'The Su-47 was a twin-engine forward-swept-wing supersonic technology demonstrator, and serial production never materialized.',
    true, false, 'Sukhoi Su-47', 'Berkut', 'role', 'medium', 'development',
    '["technology demonstrator", "forward-swept wing", "no serial production"]'::jsonb,
    '[]'::jsonb, '["military", "negative-fact", "wiki"]'::jsonb, 'proposed'
),
(
    'av_0030', 'aviation_golden_v1',
    'What is the maximum takeoff weight of the Airbus A380 according to the supplied corpus?',
    null,
    false, true, 'Airbus A380', 'unknown', 'no_answer', 'easy', 'test',
    '[]'::jsonb, '[]'::jsonb, '["unanswerable", "abstention", "out-of-corpus"]'::jsonb, 'proposed'
),
(
    'av_0031', 'aviation_golden_v1',
    'What maximum take-off weights are listed for the A320-200 WV000 through WV003 variants in the Airbus technical document?',
    'The listed maximum take-off weights are 73,500 kg for WV000, 68,000 kg for WV001, 70,000 kg for WV002, and 75,500 kg for WV003.',
    true, false, 'Airbus A320', 'A320-200', 'numeric', 'hard', 'validation',
    '["A320-200 WV000 through WV003 MTOW values"]'::jsonb,
    '[{"name":"WV000","value":73500,"unit":"kg"},{"name":"WV001","value":68000,"unit":"kg"},{"name":"WV002","value":70000,"unit":"kg"},{"name":"WV003","value":75500,"unit":"kg"}]'::jsonb,
    '["numeric", "official-manual", "variant"]'::jsonb, 'proposed'
),
(
    'av_0032', 'aviation_golden_v1',
    'What maximum landing weight is repeated for the A320-200 weight variants WV000 through WV003?',
    'The maximum landing weight is 64,500 kg (142,198 lb) for each of WV000 through WV003.',
    true, false, 'Airbus A320', 'A320-200', 'numeric', 'medium', 'validation',
    '["A320-200 maximum landing weight"]'::jsonb,
    '[{"name":"maximum_landing_weight","value":64500,"unit":"kg"},{"name":"maximum_landing_weight_imperial","value":142198,"unit":"lb"}]'::jsonb,
    '["numeric", "official-manual", "variant"]'::jsonb, 'proposed'
),
(
    'av_0033', 'aviation_golden_v1',
    'What MTOW and range improvement are stated for the A330-800 and A330-900 in the Airbus technical document?',
    'The MTOW of both the A330-800 and A330-900 was increased by 9,000 kg to 251,000 kg, giving over 600 nautical miles more range than the 242,000 kg version.',
    true, false, 'Airbus A330', 'A330-800/A330-900', 'numeric', 'hard', 'validation',
    '["A330neo MTOW 251000 kg", "over 600 nm additional range"]'::jsonb,
    '[{"name":"mtow","value":251000,"unit":"kg"},{"name":"mtow_increase","value":9000,"unit":"kg"},{"name":"range_increase","value":600,"unit":"nmi_minimum"}]'::jsonb,
    '["numeric", "official-manual", "variant"]'::jsonb, 'proposed'
),
(
    'av_0034', 'aviation_golden_v1',
    'What payload and range are stated for the A330-200F in the Airbus technical document?',
    'The A330-200F has up to 70,000 kg of payload and a range of up to 4,000 nautical miles (7,408 km).',
    true, false, 'Airbus A330', 'A330-200F', 'numeric', 'medium', 'validation',
    '["A330-200F payload", "A330-200F range"]'::jsonb,
    '[{"name":"payload","value":70000,"unit":"kg"},{"name":"range","value":4000,"unit":"nmi"},{"name":"range_metric","value":7408,"unit":"km"}]'::jsonb,
    '["numeric", "freighter", "official-manual", "variant"]'::jsonb, 'proposed'
),
(
    'av_0035', 'aviation_golden_v1',
    'Which sections of the Boeing 747-400 airport-planning document cover general dimensions for the 747-400 and its freighter variants?',
    'Section 2.2.1 covers the 747-400, 747-400 Combi, and 747-400ER, while section 2.2.2 covers the 747-400 Freighter and 747-400ER Freighter.',
    true, false, 'Boeing 747', '747-400', 'document_structure', 'medium', 'validation',
    '["section 2.2.1 passenger/combi/ER dimensions", "section 2.2.2 freighter dimensions"]'::jsonb,
    '[]'::jsonb, '["official-manual", "document-structure", "pdf-text"]'::jsonb, 'proposed'
),
(
    'av_0036', 'aviation_golden_v1',
    'How far can the B-52 fly without refueling and how much ordnance can it carry according to the Congressional Research Service report?',
    'The B-52 can fly 8,800 miles without refueling and carry 70,000 lb of ordnance.',
    true, false, 'B-52 Stratofortress', 'B-52', 'numeric', 'easy', 'validation',
    '["B-52 range without refueling", "B-52 ordnance capacity"]'::jsonb,
    '[{"name":"range","value":8800,"unit":"mi"},{"name":"ordnance","value":70000,"unit":"lb"}]'::jsonb,
    '["numeric", "official-report", "military", "pdf-text"]'::jsonb, 'proposed'
)
on conflict (case_id) do nothing;

delete from evaluation.evidence
where case_id in ('av_0017', 'av_0018', 'av_0019');

insert into evaluation.evidence (
    case_id, source_file, document_id, line_start, line_end, quote, relevance
)
values
('av_0001', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 1, 1, 'The A320 aircraft programme was launched in March 1984, first flew on 22 February 1987, and was introduced in April 1988 by Air France.', 3),
('av_0002', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 2, 2, 'The first member of the family was followed by the stretched A321 (first delivered in January 1994), the shorter A319 (April 1996), and the shortest variant, the A318 (July 2003).', 3),
('av_0003', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 4, 4, 'The twinjet has a six-abreast economy cross-section and came with either CFM56-5A or -5B, or IAE V2500 turbofan engines, except the A318. The A318 has either two CFM56-5B engines or a pair of PW6000 engines in place of the IAE V2500.', 3),
('av_0004', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 5, 5, 'The family pioneered the use of digital fly-by-wire and side-stick flight controls in airliners.', 3),
('av_0005', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 6, 6, 'Variants offer maximum take-off weights from 68 to 93.5 tonnes (150,000 to 206,000 lb), with a range of 5,740–6,940 kilometres (3,570–4,320 mi; 3,100–3,750 nmi).', 3),
('av_0006', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 7, 7, 'The 31.4 m (103 ft) long A318 typically accommodates 107 to 132 passengers.', 3),
('av_0007', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 9, 9, 'The A320 is 37.6 m (123 ft) long and can accommodate 150 to 186 passengers.', 3),
('av_0008', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 9, 10, 'The A320 is 37.6 m (123 ft) long and can accommodate 150 to 186 passengers. The 44.5 m (146 ft) A321 offers 185 to 230 seats.', 3),
('av_0009', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 12, 12, 'With more efficient turbofans and improvements including "sharklet" winglets, it offers up to 15% better fuel economy.', 3),
('av_0010', 'data/raw/wiki/Airbus_A320_family.txt', '2aa41026a0ad2790', 194, 195, 'The A321-100 maximum takeoff weight is increased by 9,600 kg (21,200 lb) to 83,000 kg (183,000 lb).', 3),
('av_0011', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 2, 2, 'The A330-300, the first variant, took its maiden flight in November 1992 and entered service with Air Inter in January 1994.', 3),
('av_0012', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 3, 3, 'The A330 was Airbus''s first airliner to offer a choice of three engines: the General Electric CF6, Pratt & Whitney PW4000, or the Rolls-Royce Trent 700.', 3),
('av_0013', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 3, 3, 'The A330-300 has a range of 11,750 km (6,340 nmi; 7,300 mi) with 277 passengers, while the shorter A330-200 can cover 13,450 km (7,260 nmi; 8,360 mi) with 247 passengers.', 3),
('av_0014', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 4, 4, 'The A330neo (new engine option) comprising the A330-800 and -900', 3),
('av_0015', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 96, 96, 'Its MTOW grew from 212 tonnes (467,000 lb) at introduction to 242 tonnes (534,000 lb) in 2015', 3),
('av_0016', 'data/raw/wiki/Airbus_A330.txt', '32c0e25274f78e18', 128, 128, 'The freighter has a range of 7,400 km (4,000 nmi; 4,600 mi) with a 65 tonnes (140,000 lb) payload, or 5,900 km (3,200 nmi; 3,700 mi) with 70 tonnes (150,000 lb).', 3),
('av_0017', 'data/raw/wiki/Boeing_747.txt', 'f3d8f5418129b47f', 2, 2, 'The 747''s first flight took place on February 9, 1969, and the 747 was certified in December 1969. It entered service with Pan Am on January 22, 1970.', 3),
('av_0018', 'data/raw/wiki/Boeing_747.txt', 'f3d8f5418129b47f', 3, 3, 'With a ten-abreast economy seating, it typically accommodates 366 passengers in three travel classes. It has a pronounced 37.5° wing sweep, allowing a Mach 0.85 (490 kn; 900 km/h) cruise speed', 3),
('av_0019', 'data/raw/wiki/Boeing_747.txt', 'f3d8f5418129b47f', 4, 4, 'The stretched 747-8 was launched on November 14, 2005, using the General Electric GEnx engine first developed for the 787 Dreamliner.', 3),
('av_0020', 'data/raw/wiki/Boeing_747-8.txt', '8379b78c476be73b', 5, 5, 'reaching a total length of 250 feet (76 m) ... its maximum takeoff weight (MTOW) increases to 975,000 pounds (442 t)', 3),
('av_0021', 'data/raw/wiki/Boeing_747-8.txt', '8379b78c476be73b', 6, 6, 'The freighter version, with a shorter upper deck, can haul 308,000 pounds (140 t) over 4,120 nautical miles', 3),
('av_0022', 'data/raw/wiki/Boeing_747-8.txt', '8379b78c476be73b', 7, 7, 'The intercontinental version can carry 467 passengers in a typical three-class configuration with a range of 7,790 nautical miles', 3),
('av_0023', 'data/raw/wiki/Chengdu_J-20.txt', '8958ef26f99674ec', 1, 2, 'The aircraft has three notable variants: the initial production model, the revised airframe variant with new engines and thrust-vectoring control, and the aircraft-teaming capable twin-seat variant. ... the aircraft made its maiden flight on 11 January 2011 ... entered service in March 2017', 3),
('av_0024', 'data/raw/wiki/Chengdu_J-20.txt', '8958ef26f99674ec', 1, 1, 'The aircraft has three notable variants: the initial production model, the revised airframe variant with new engines and thrust-vectoring control, and the aircraft-teaming capable twin-seat variant.', 3),
('av_0025', 'data/raw/wiki/General_Dynamics_F-16_Fighting_Falcon.txt', '9009b601c039f982', 3, 3, 'The F-16''s key features include a frameless bubble canopy for enhanced cockpit visibility, a side-stick ... an ejection seat reclined 30 degrees from vertical ... relaxed static stability/fly-by-wire flight control system', 3),
('av_0026', 'data/raw/wiki/Lockheed_Martin_F-35_Lightning_II.txt', '889e6e17383bb17e', 1, 1, 'The aircraft has three main variants: the conventional takeoff and landing F-35A, the short take-off and vertical-landing F-35B, and the catapult-assisted take-off but arrested recovery F-35C.', 3),
('av_0027', 'data/raw/wiki/Lockheed_Martin_F-22_Raptor.txt', 'c75c80e52557a791', 2, 2, 'First flown in 1997 ... formally entered service in December 2005 as the F-22A.', 3),
('av_0028', 'data/raw/wiki/Eurofighter_Typhoon.txt', 'e4d0532c25999e3b', 1, 1, 'The Typhoon was designed originally as an air-superiority fighter', 3),
('av_0029', 'data/raw/wiki/Sukhoi_Su-47.txt', 'cd46168e61cc19f8', 1, 2, 'The Sukhoi Su-47 Berkut is a Russian twin-engine, forward-swept wing, supersonic technology demonstrator ... serial production of the type never materialized', 3),
('av_0031', 'data/raw/pdf_to_txt/AC_A320_0624.txt', 'b0132e331549708b', 1500, 1524, 'Aircraft Characteristics WV000 WV001 WV002 WV003 Maximum Take-Off Weight (MTOW) 73 500 kg (162 040 lb) 68 000 kg (149 914 lb) 70 000 kg (154 324 lb) 75 500 kg (166 449 lb)', 3),
('av_0032', 'data/raw/pdf_to_txt/AC_A320_0624.txt', 'b0132e331549708b', 1525, 1533, 'Maximum Landing Weight (MLW) 64 500 kg (142 198 lb) 64 500 kg (142 198 lb) 64 500 kg (142 198 lb) 64 500 kg (142 198 lb)', 3),
('av_0033', 'data/raw/pdf_to_txt/ac_a330_jul2023_0.txt', '0c49df4217a0a457', 1943, 1950, 'The latest member of the A330 family is the A330neo, incorporating the latest-generation Rolls-Royce Trent 7000 engines ... the MTOW of both the A330-800 and A330-900 has been increased by 9 000 kg (19 842 lb) to 251 000 kg (553 360 lb) giving over 600 nm (1 111 km) more range', 3),
('av_0034', 'data/raw/pdf_to_txt/ac_a330_jul2023_0.txt', '0c49df4217a0a457', 1956, 1958, 'The new generation mid-size freighter, the A330-200F, has up to 70 000 kg (154 324 lb) payload and a range of up to 4 000 nm (7 408 km).', 3),
('av_0035', 'data/raw/pdf_to_txt/747-400_Rev_F.txt', '614c93091d6bc1a2', 3047, 3057, '2.2 GENERAL DIMENSIONS 2.2.1 General Dimensions: Model 747-400, -400 Combi, -400ER 2.2.2 General Dimensions: Model 747-400 Freighter, -400ER Freighter', 3),
('av_0036', 'data/raw/pdf_to_txt/IF12945.7.txt', 'e470f1e3b9a4845f', 62, 68, 'The B-52, which entered service in 1955, is a long-range heavy bomber that can fly 8,800 miles without refueling. ... The B-52 can carry 70,000 lb. of ordnance.', 3)
on conflict (case_id, source_file, line_start, line_end, quote) do nothing;
