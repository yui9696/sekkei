# Internal document search with summaries

Employees must find internal documents quickly and get a short summary without opening them.

## Functional
- Employees upload PDF and Markdown documents (up to 20 MB) and tag them with a team.
- The system extracts the text, splits it into chunks, computes embeddings and indexes them for semantic search.
- Employees search with a natural-language query and get the ten best passages with links to the documents.
- For each result the system generates a three-sentence summary with an LLM and caches it.
- Team leads can delete documents; deleted documents disappear from search results within one minute.
- Every search query is logged with the employee id for usage reporting; a weekly report is emailed to the knowledge team.

## Non-functional
- Search returns within 800 ms p95 for a corpus of 50,000 documents.
- Embedding and summary generation must not block uploads; an upload is acknowledged within 1 s.
- Documents are visible only to members of the tagged team.

## Constraints
- Python 3.12, PostgreSQL with pgvector available, S3-compatible object storage available. Team of 3.
- Embeddings and summaries come from an external API with a rate limit of 60 requests per minute.
- Employees authenticate through the company SSO (OIDC).
