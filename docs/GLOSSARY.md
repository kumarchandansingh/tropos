# Tropos technical glossary

This glossary expands shorthand used across Tropos product, architecture, delivery, quality, and learning documents. Technical abbreviations should be written in full on first use where practical and may use the abbreviation afterward.

| Term | Full form | Plain-English meaning |
| --- | --- | --- |
| AI | Artificial Intelligence | A broad term for software that performs tasks associated with human intelligence, including language models and retrieval systems. |
| ACL | Access Control List | Rules describing who may access a resource. In Tropos this is represented through tenant, scope, and allowed groups rather than a literal operating-system ACL structure. |
| ADR | Architecture Decision Record | A short document that records an architectural decision, the alternatives considered, the trade-offs, and the reason for the choice. |
| ANN | Approximate Nearest Neighbor | A family of techniques for finding vectors that are probably among the closest without comparing against every vector exactly. |
| API | Application Programming Interface | A defined interface through which software components call one another. |
| BM25 | Best Matching 25 | A lexical ranking algorithm that scores documents from query-term frequency, rarity, and document-length normalization. |
| BOM | Byte Order Mark | A byte sequence that may appear at the beginning of encoded text and can affect deterministic text handling. |
| CI/CD | Continuous Integration / Continuous Delivery or Deployment | The automated path for validating changes and, where configured, promoting or deploying them. |
| CI | Continuous Integration | Automated checks such as formatting, linting, type checking, tests, and package builds that run on repository changes. |
| CR | Carriage Return | A control character used in some newline conventions. |
| CRLF | Carriage Return + Line Feed | The two-character newline convention common on Windows. |
| DB | Database | Persistent structured storage. |
| DOCX | Office Open XML Word document | The modern Microsoft Word document format, packaged internally as ZIP + XML. |
| ETag | Entity Tag | An HTTP validator used for conditional requests and cache/change detection. |
| FTS | Full-Text Search | Search over indexed text rather than scanning every document. |
| FTS5 | SQLite Full-Text Search version 5 | SQLite's full-text indexing module used by Tropos for lexical retrieval. |
| HNSW | Hierarchical Navigable Small World | A graph-based approximate nearest-neighbor index for vector search. |
| HTML | HyperText Markup Language | Markup used to represent web documents. |
| HTTP | Hypertext Transfer Protocol | The protocol commonly used for web APIs and services. |
| ID | Identifier | A value used to distinguish one object or record from another. |
| IVF | Inverted File Index | A vector-search approach that groups vectors into coarse clusters and searches selected clusters. |
| IVFFlat | Inverted File with flat vectors | A practical IVF variant that stores full vectors within the selected clusters. |
| JSON | JavaScript Object Notation | A structured text format used for deterministic serialization and API payloads. |
| K in top-K / Recall@K | Cutoff count | The number of highest-ranked results considered. Recall@5 asks whether relevant evidence appears within the first five results. |
| L2 | Euclidean distance / norm | Straight-line distance in vector space. |
| LF | Line Feed | The newline character commonly used on Unix-like systems. |
| LLM | Large Language Model | A generative model that predicts and produces language. |
| MMR | Maximum Marginal Relevance | A ranking method that balances relevance with diversity so top results are not near-duplicates. |
| MRR | Mean Reciprocal Rank | A retrieval metric that rewards placing the first relevant result near the top. |
| NFC | Unicode Normalization Form C | A standard Unicode normalization form that composes equivalent character sequences into a consistent representation. |
| OCR | Optical Character Recognition | Conversion of text in images or scanned documents into machine-readable text. |
| PDF | Portable Document Format | A document format that preserves layout and can contain text, images, or scanned pages. |
| PQ | Product Quantization | A vector-compression technique often used to reduce memory and speed approximate vector search. |
| RAG | Retrieval-Augmented Generation | A pattern where retrieved evidence is supplied to a language model before it generates an answer. |
| RRF | Reciprocal Rank Fusion | A way to combine ranked lists using rank positions rather than trying to compare raw scores from different retrievers. |
| SHA-256 | Secure Hash Algorithm, 256-bit | A cryptographic hash function that produces a deterministic 256-bit fingerprint. |
| SQL | Structured Query Language | The language used to query and modify relational databases. |
| SQS | Amazon Simple Queue Service | A managed message-queue service; standard queues can deliver messages more than once. |
| TXT | Plain-text file | A file that stores text without rich document structure. |
| UTF-8 | Unicode Transformation Format, 8-bit | A widely used encoding for Unicode text. |
| ZIP | ZIP archive format | A compressed archive/container format. DOCX files are ZIP packages containing XML and related assets. |
| XML | Extensible Markup Language | A structured markup format used inside DOCX and many enterprise formats. |
| p50 / p95 | 50th / 95th percentile | Latency percentiles used to show typical and tail performance rather than only an average. |
| O(N) | Linear-time growth | Work increases roughly in proportion to the number of items N; an exact vector scan compares against every eligible vector. |

## Terms that are names rather than acronyms

- **SQLite** is the name of the embedded relational database used in the current Tropos foundation.
- **pgvector** is the PostgreSQL vector extension.
- **LangChain** is a framework/ecosystem for language-model applications.
- **Tropos Resolve** is the knowledge-resolution capability within Tropos.
