# Practice quiz for STU0003

This quiz covers two competencies marked as gaps: 'Data Structures and Algorithms' (persistent gap) and 'Object-Oriented Design and Implementation' (isolated gap). These questions are practice only and not part of any formal assessment.

> The grounding checks confirm every question is tied to one of this student's own gaps,
> SILOs and assessments. They do not confirm the marked answer is correct: a member of
> staff should check the answer key before a student uses this.

## 1. Data Structures and Algorithms (persistent gap)

*CSE2ALG, CSE2ALG:SILO2, pitched at CSE2ALG:Test*

In a computing context, which of the following is the most appropriate data structure for efficiently storing and retrieving a set of unique, sorted integers where fast lookup and insertion are required?

- A. Array
- B. Hash table
- C. Binary search tree
- D. Linked list

## 2. Data Structures and Algorithms (persistent gap)

*CSE2ALG, CSE2ALG:SILO3, pitched at CSE2ALG:Assignment*

When implementing a sorting algorithm in Java to sort an array of integers, which of the following is the most appropriate choice for ensuring the algorithm is both efficient and stable?

- A. Quick sort
- B. Merge sort
- C. Heap sort
- D. Bubble sort

## 3. Object-Oriented Design and Implementation (isolated gap)

*CSE1OOF, CSE1OOF:SILO1, pitched at CSE1OOF:Test*

In object-oriented modelling, which of the following best describes the relationship between a 'Car' object and a 'Wheel' object when a car has four wheels?

- A. Inheritance
- B. Composition
- C. Aggregation
- D. Association

## 4. Object-Oriented Design and Implementation (isolated gap)

*CSE1OOF, CSE1OOF:SILO3, pitched at CSE1OOF:Assignment*

Which of the following is the best example of code sharing and reuse through object-oriented techniques to reduce development time?

- A. Writing a new method for each similar task
- B. Using inheritance to extend a base class
- C. Copying and pasting code from one file to another
- D. Creating a new class for every function

## Answers

**1.** C. The correct answer is 'Binary search tree' because it supports efficient insertion, deletion, and lookup operations in O(log n) average time, and maintains elements in sorted order, which aligns with the SILO's focus on identifying data structures in computing contexts. The most tempting distractor, 'Hash table', provides fast average-case lookup and insertion but does not maintain order, making it less suitable for sorted retrieval. This question targets CSE2ALG:SILO2.

**2.** B. The correct answer is 'Merge sort' because it has a time complexity of O(n log n) and is stable, meaning it preserves the relative order of equal elements, which aligns with the SILO's focus on implementing data structures and sorting algorithms in Java. The most tempting distractor, 'Quick sort', is efficient but unstable and has a worst-case time complexity of O(n²), making it less reliable. This question targets CSE2ALG:SILO3.

**3.** B. The correct answer is 'Composition' because a 'Car' object is composed of 'Wheel' objects, and the wheels cannot exist independently of the car, which aligns with the SILO's focus on analysis/design/implementation compared with object-oriented modelling using objects that combine data structure and behaviour. The most tempting distractor, 'Aggregation', implies a 'has-a' relationship where the parts can exist independently, which is not the case here. This question targets CSE1OOF:SILO1.

**4.** B. The correct answer is 'Using inheritance to extend a base class' because it allows new classes to inherit properties and methods from existing ones, promoting code reuse and reducing development time, which aligns with the SILO's focus on code sharing and reuse through object-oriented techniques. The most tempting distractor, 'Copying and pasting code', leads to redundancy and maintenance issues, violating the principles of object-oriented design. This question targets CSE1OOF:SILO3.

## Educator notes (blind check)

A second pass (provider=openai_compatible model=qwen/qwen3-vl-30b base_url=http://localhost:1234/v1/ temperature=0.2 max_tokens=16000) answered each question without seeing the key, then wrote a teaching explanation. It chose the author's answer on every question.

**1.** Blind answer C (high confidence), agrees with the key.

A binary search tree (BST) is the most appropriate data structure for storing unique, sorted integers with fast lookup and insertion because it maintains order and allows O(log n) average-case time complexity for both operations. Arrays and linked lists don’t maintain order efficiently for lookup, and hash tables don’t preserve sorting. Hash tables are fast for lookup and insertion but don’t maintain order, so they’re not suitable when sorted access is required. This question practices identifying the right data structure for a given computational need, which is key to SILO2.

**2.** Blind answer B (high confidence), agrees with the key.

Merge sort is the best choice because it is both efficient (O(n log n) time complexity) and stable (it preserves the relative order of equal elements), which is important for sorting integers. Quick sort is fast but unstable and has poor worst-case performance. Heap sort is efficient but not stable. Bubble sort is inefficient (O(n²)) and not suitable for large datasets. This question practices selecting the right algorithm based on performance and stability, aligning with SILO3.

**3.** Blind answer B (high confidence), agrees with the key.

Composition best describes the relationship between a 'Car' and 'Wheel' because the wheels are part of the car and cannot exist independently. In composition, the part is dependent on the whole, which matches the real-world scenario where wheels are created and destroyed with the car. Inheritance is about 'is-a' relationships, aggregation is a weaker 'has-a' relationship, and association is too general. This question practices identifying object-oriented relationships, which is central to SILO1.

**4.** Blind answer B (high confidence), agrees with the key.

Using inheritance to extend a base class is the best example of code reuse because it allows new classes to inherit and build upon existing functionality without duplicating code. Copying and pasting code or creating new classes for every function leads to redundancy and maintenance issues. Writing new methods for similar tasks doesn’t promote reuse. This question practices understanding how object-oriented techniques reduce development time, which is the focus of SILO3.

## The subjects

- **CSE1OOF** Object-Oriented Programming Fundamentals. The Object-Oriented (OO) paradigm is a significant influence in software development in the computer industry. It divides a system into objects that exist in the model of the application domain. In this subject, students will be introduced to OO concepts, terminologies, syntax and programming using Java.

- **CSE2ALG** Algorithms and Data Structures. This subject covers a range of important algorithms and data structures. Data structures for implementing containers are covered and include linear structures, tree structures and hash tables. Algorithms for insertion and deletion of elements, and algorithms for searching and sorting on these structures are covered where appropriate. Graphs and graph algorithms are also covered. Students will learn the construction and workings of the data structures and algorithms covered.

- **CSE3CAP** Capstone Project. This subject enables you to develop your skills to implement a small or medium-sized project in a team. You will address a real-life problem in software engineering or cybersecurity. The subject covers the skills to manage, implement and report on the delivery of a substantive project to appropriate stakeholders. You will make milestone presentations with your team.

## The evidence this quiz was grounded in

| Competency | Classification | Attainment | Per subject |
| --- | --- | --- | --- |
| Object-Oriented Design and Implementation | isolated gap | 62.7% | CSE1OOF 62.7% |
| Data Structures and Algorithms | persistent gap | 63.7% | CSE1OOF 62.7%, CSE2ALG 64.1% |
| Industry Standards Application | developing | 65.0% | CSE3CAP 65.0% |
| Technical Communication and Documentation | developing | 65.1% | CSE3CAP 65.1% |
| Project Management | proficient | 66.0% | CSE3CAP 66.0% |
