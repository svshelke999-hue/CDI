```mermaid
    flowchart TD

    A[Clinical Data Available] --> B[Clinical NLP / LLM Extraction]

    B --> C[Primary Guideline Engine]

    C --> C1[Apply ICD-10-CM / PCS Guidelines]
    C --> C2[Apply AHA Coding Clinic Rules]
    C --> C3[Apply CMS MS-DRG Logic]
    C --> C4[Apply NCCI Edits]

    C1 --> D
    C2 --> D
    C3 --> D
    C4 --> D

    D{Clinically and Coding Valid?}

    D -- No --> E[Suppress CDI Prompts]
    D -- Yes --> F[Identify Documentation Gaps]

    F --> G{Is Payer Known?}

    G -- No --> H[Use General Guidelines Only]
    G -- Yes --> I[Load Payer-Specific Rule Pack]

    I --> J[Apply Payer Coverage and Medical Necessity Rules]

    J --> K{Payer Rules Satisfied?}

    K -- Yes --> L[Generate General and Payer Aligned Prompt]
    K -- No --> M[Generate Documentation Requirement Prom]()
```   
