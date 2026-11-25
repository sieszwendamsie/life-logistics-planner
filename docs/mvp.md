# Poland ↔ Italy Travel and Logistics Assistant

## 1. Goal

The assistant should plan and optimize recurring trips and stays between Poznań, Poland, and Italy. It must consider hybrid work, family commitments, accommodation availability, transport options, and costs at the same time.

Its purpose is to replace the manual process of searching for connections, comparing dates, and transferring the final arrangements into Google Calendar.

## 2. Recurring travel pattern

- Typical stay in Italy: approximately 3–4 weeks.
- Typical interval between trips: approximately 4–5 weeks.
- Regular presence at the office in Italy is required.
- The plan must account for dates when I need or prefer to be in Poznań.
- Travelling together as a family is preferred, but travelling alone must also be possible.

## 3. Constraints and input data

| Area | Requirements |
|---|---|
| Calendar | Work commitments, meetings, family plans, and important events |
| Office | Dates when being physically present at the Italian office is required or preferred |
| Family | Dates when we travel together and when we may travel separately |
| Accommodation | Availability of our preferred rented apartment |
| Alternative accommodation | Airbnb, hotels, and other apartments |
| Flights | Ryanair, Wizz Air, Momondo, and other available sources |
| Transport | Airport transfers, local transport, driving, and car rental |
| Costs | Flights, accommodation, car rental, fuel, parking, and other expenses |
| Time | Total door-to-door travel time and transport-related inconvenience |

## 4. Expected workflow

When planning the next travel period, the assistant should:

1. Review the calendar and identify relevant constraints.
2. Check the availability of the preferred apartment.
3. Identify feasible travel dates.
4. Search for flights and alternative transport options.
5. If the preferred apartment is unavailable, prepare an alternative where I travel alone first and my family joins later.
6. Compare feasible combinations of dates, flights, accommodation, and transport.
7. Present a shortlist of recommended travel options.

## 5. Expected output

The assistant should not provide only one proposed departure date. It should allow me to compare several realistic alternatives visually.

Example comparison:

| Criteria | Option A | Option B | Option C |
|---|---|---|---|
| Dates | 24 Nov–20 Dec | 27 Nov–23 Dec | 1 Dec–28 Dec |
| Flights | Available | Available | Available |
| Accommodation | Available | Unavailable | Available |
| Family travel | Together | Separately | Together |
| Office commitments | Satisfied | Satisfied | Satisfied |
| Total cost | € | €€ | €€€ |
| Travel time | h | h | h |

The interface should also provide:

- A visual timeline showing time in Poland and Italy, family plans, office commitments, accommodation, and travel.
- A map and transport details.
- The total estimated cost for each option.
- The advantages and disadvantages of each option.
- A recommended option with a clear explanation of the trade-offs.

## 6. Integrations and automation

The long-term assistant should be able to:

- Read events from Google Calendar.
- Find and present flight, accommodation, and transport options.
- Calculate total costs and travel times.
- Accept changes to requirements through conversation, for example: “I need to stay in Poznań two days longer.”
- Recalculate the options whenever a requirement changes.
- Add the selected plan to Google Calendar after my approval.

**Autonomy boundary:** the assistant may search, analyze, compare, and prepare booking proposals independently. Purchasing tickets and confirming accommodation must require my explicit approval.

## 7. MVP scope and product direction

The format described in this document is the **MVP (Minimum Viable Product)**: the smallest useful version that can test whether the planning workflow solves the real problem.

The MVP should focus on the core planning loop:

1. Enter or import calendar constraints.
2. Add or check accommodation availability.
3. Enter or collect candidate travel options.
4. Generate and compare a small number of feasible alternatives.
5. Review the timeline, costs, and trade-offs.
6. Approve one option and transfer it to Google Calendar.

The MVP does not need full autonomous booking, comprehensive integrations, or a fully autonomous AI agent. Those capabilities can be introduced incrementally after the core planning process has been tested and proven useful.

## 8. Core product principle

This should not be another holiday-planning application.

It should be a **personal logistics planning system for managing life and hybrid work across two countries**.

Its primary job is to find a good solution across multiple constraints and competing priorities, not simply to find the cheapest flight.

**Success metric:** instead of spending several hours manually planning the next stay, I should spend around 15 minutes reviewing and approving the proposed options.
