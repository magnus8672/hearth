"""Frozen synthetic routing evaluation, grouped split to avoid identical templates across sets.

These 360 labeled English cases measure this narrow intent task, not general model quality.
Threshold .85, macro F1 .90, media precision .99 and p95 250 ms were frozen before scoring.
"""
TOPICS = ['a garden', 'a school', 'a library', 'a robot', 'a train', 'a bakery', 'a boat', 'a museum']
TEMPLATES = {
    'chat.general': [
        'Hello there! How are you today? I visited {topic}.',
        'What are the practical benefits of {topic}?',
        'I am curious about the history of {topic}. Tell me about it.',
        'Do you know any interesting facts about {topic}?',
        'Why do people enjoy spending time around {topic}?',
    ],
    'reason.plan': [
        'How should I organize the next three weeks to launch {topic}? Give milestones.',
        'I need a sequence of tasks and a schedule for building {topic}.',
        'Help me break the work for {topic} into a practical strategy.',
        'Put together a step by step project plan for {topic}.',
        'We have a month to open {topic}. What should we do each week?',
    ],
    'code.implement': [
        'I need Python code that counts visitors to {topic}.',
        'The JavaScript counter for {topic} throws a TypeError. Fix it: const n = null; n.length;',
        'Could you implement a Rust function to sort the inventory of {topic}?',
        'Build me a SQL query that returns the ten most visited exhibits at {topic}.',
        'Please turn this into a working Python program for {topic}: read a CSV and add all the price values.',
    ],
    'code.explain': [
        'What does this Python expression do for {topic}: sorted(items, key=lambda x: x.price)?',
        'Review this function used at {topic} for bugs, without rewriting it: def add(a,b): return a-b',
        'Walk me through the algorithm in this code for {topic}: for i in range(n): total += i',
        'Explain why this JavaScript code used in {topic} fails: const x=null; x.length;',
        'Describe how this SQL statement used at {topic} works: SELECT name FROM things ORDER BY name;',
    ],
    'write.compose': [
        'Draft an invitation to the opening of {topic}.',
        'I need a short poem about {topic}.',
        'Compose a friendly email asking for a tour of {topic}.',
        'Turn this rough sentence into polished prose: {topic} was very nice and we liked it.',
        'Tell a short fictional story set in {topic}, in a warm voice.',
    ],
    'text.summarize': [
        'Shorten this passage to one sentence: We visited {topic} on Monday. It was busy. We returned on Tuesday.',
        'Give me the main points of this report: {topic} opened in June. Staff hired five people. Attendance doubled.',
        'Condense this update: The team at {topic} completed repairs, added lighting, painted the entry, and reopened.',
        'Summarize this note in ten words: We had a pleasant morning at {topic}, followed by a long walk home.',
        'Make a brief abstract of this text: {topic} tested three schedules. Afternoon visits attracted more families.',
    ],
    'data.extract': [
        'Return only the dates and names as JSON: Ada visited {topic} on June 4. Sam went on June 6.',
        'Pull out the invoice number and amount: {topic}, invoice A123, total 42 dollars.',
        'Extract the email address from this record: {topic}, contact person@example.invalid.',
        'Convert these details to structured fields, without commentary: venue {topic}; guests 18; date July 9.',
        'List each named person from this paragraph: Ada and Sam inspected {topic}. Chris stayed home.',
    ],
    'image.generate': [
        'Please generate a picture of {topic} in watercolor.',
        'I would like you to make a new image showing {topic} at sunset.',
        'Render an illustration of {topic} for me now.',
        'Create a photograph style image of {topic} surrounded by flowers.',
        'Draw me a picture of {topic} under a starry sky.',
    ],
    'uncertain': [
        'Do that again with {topic}.',
        'Change it to {topic}, please.',
        'Make the background transparent in the existing picture of {topic}.',
        'Generate a 3D mesh of {topic}, not a picture.',
        'The other one about {topic}, please.',
    ],
}
CASES = [{'id': f'{label}-{template}-{topic}', 'split': 'tune' if template < 2 else 'held_out',
          'label': label, 'text': phrase.format(topic=subject)}
         for label, phrases in TEMPLATES.items() for template, phrase in enumerate(phrases)
         for topic, subject in enumerate(TOPICS)]
