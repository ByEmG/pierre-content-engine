# Facts the engine may use

Only facts written here (or in a note you send the bot) can appear in a post.
Every number in a draft must match a number in this file or in a source note,
or the fact guard blocks it. Edit this file as your work moves on.

## Afryx Labs
- I founded Afryx Labs and run it alone. Title: Founder and Technical Lead.
- Afryx Labs is a client delivery consultancy: we turn client problems into working software.
- Started April 2026. Works between Leeds and Yaoundé, Cameroon.

## Kampus (client: the Fang group)
- Kampus is a school management platform built for Fang, a private education group in Cameroon.
- Fang has 3 institutions: Institut Privé Fang, Institut Supérieur Fang and Centre de Formation Fang. Each needs its own tailored software.
- Delivered jointly by Afryx Labs and Kaeyros Analytics as one team of 15.
- I lead requirements gathering and direct delivery alongside the Kaeyros technical lead.
- Weekly client loop: demo progress, capture changes and missing features, reprioritise with the team, present the next iteration.
- 16 client meetings so far.
- The project is in active build. Do not say it is live or in production.
- The client is happy to be named.

## MenoClinic (client project, UK private menopause clinic)
- An AI-assisted patient screening tool for a UK private menopause clinic.
- I am technical lead, architect and the sole point of contact with the clinic's founder, a registered independent prescriber.
- Team of 3.
- Architecture: deterministic red-flag rules decide safety, an AI drafts a summary linked to the patient's original answers, and a clinician signs off every case.
- Targets agreed with the client before build: 100% red-flag sensitivity, 85 to 95% triage accuracy, at least 50% screening time saved.
- Tested on clinician-approved synthetic cases, never real patient data.
- The first phase stays separate from the clinic's live booking system. UK GDPR and clinical safety requirements captured from the start.
- RESTRICTED: never name the clinic or its founder. Say "a UK private clinic".

## pierre-agent-evals (open source, github.com/ByEmG/pierre-agent-evals)
- A Python harness that runs an AI agent through a task suite and scores each run with programmatic checks and an LLM judge.
- Tracks pass rate, cost and latency.
- Classifies failures with a 6-category taxonomy, for example planning failure and premature termination.
- Controlled test: cutting the agent's step budget from 10 to 3 dropped the pass rate from 8/8 to 5/8. Every failure was premature termination.
- Found and fixed a configuration bug in the test runner and added a regression test.
- Built January to March 2025.

## SiteDue
- A web app that turns completed field jobs into billing-ready records for UK commercial electrical maintenance firms.
- I am technical and product lead in a team of 5.
- Built with React and Supabase. Shaped from customer interviews.

## Parkinson's detection
- A classification pipeline comparing Random Forest, SVM and XGBoost to detect Parkinson's disease.
- October 2024 to February 2025.

## This content engine
- A Python multi-agent pipeline: planner, hook writer, writer, editor, fact guard, scorer and designer.
- Drafts only from my own work and notes, never from news.
- A scorer grades every draft out of 100 and sends weak ones back for another pass.
- I approve every post on Telegram before it goes live.

## Me
- Languages: English, French, Spanish.
- Skills: Python, TypeScript, SQL, Claude and OpenAI APIs, LangGraph, Supabase, React.
- Working towards graduate Solutions Engineer, Implementation Engineer and Technology Consultant roles.
