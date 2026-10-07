def read(page, anchor, limit=1800):
    from app.rag.research_source_spans import read_source_spans
    return read_source_spans(page, anchors=(anchor,), max_chars=limit)


def test_faq_answer_keeps_its_question_not_the_neighbor_condition():
    page = 'Q: Foreign spouses?\nA: Provide a passport.\n\nQ: How to apply?\nA: Apply online.\n'
    span, = read(page, 'Apply online')
    assert 'How to apply?' in span.content
    assert 'Foreign' not in span.content + span.heading_context
    assert span.complete and page[span.start:span.end] == span.content


def test_table_row_keeps_literal_category_header():
    page = '# Documents\n| Applicant | Required document |\n| --- | --- |\n| Foreign spouse | Passport or visa |\n| Child | Birth certificate |\n'
    span, = read(page, 'Passport')
    assert 'Applicant | Required document' in span.heading_context
    assert 'Foreign spouse' in span.content
    assert 'Child' not in span.content


def test_document_table_retains_parent_workflow_heading():
    page = ('# Withdrawal guide\n\n## Leaving the country\n\n'
        '### Required Documents\n\n| Document | Purpose |\n| --- | --- |\n'
        '| Passport | Identification |\n\n## Education withdrawal\nOther instructions.\n')
    span, = read(page, 'Passport')
    assert 'Leaving the country' in span.heading_context
    assert 'Education withdrawal' not in span.heading_context


def test_plain_child_document_heading_retains_markdown_workflow_parent():
    page = '# Leaving Country\n\nRequired Documents\n\n| Document | Purpose |\n| --- | --- |\n| Passport | ID |\n'
    span, = read(page, 'Passport')
    assert 'Leaving Country' in span.heading_context


def test_category_list_and_flat_faq_are_not_detached():
    page = '## Adopted children\nRequired documents:\n- MyKid\n- Adoption certificate\n\n## Application\nApply online.\n'
    span, = read(page, 'Adoption certificate')
    assert 'Adopted children' in span.heading_context + span.content
    assert 'Required documents' in span.content
    assert 'Apply online' not in span.content
    flat = '1. S: Who qualifies? J: Eligible households. 2. S: How to apply? J: No separate application is required.'
    span, = read(flat, 'No separate')
    assert 'How to apply?' in span.content and 'Who qualifies?' not in span.content


def test_long_unit_fragments_keep_identity_and_cannot_claim_complete_list():
    page = '## Conditional documents\n' + '\n'.join(f'- Required document {i}: ' + 'x' * 50 for i in range(60))
    first, = read(page, 'document 2:', 300)
    later, = read(page, 'document 40:', 300)
    assert first.unit_id == later.unit_id and first.document_hash == later.document_hash
    assert not first.complete and not later.complete
    assert first.content != later.content
    assert len(later.content) + len(later.heading_context) <= 300


def test_plain_section_titles_preserve_complete_eligibility_and_application_units():
    page = ('Programme overview\n\n' + 'Overview text. '*150 +
        '\n\nEligibility\n\nApproved programme recipients qualify.\n\n'
        'How To Apply\n\nNo separate application is required.\n\n'
        'Required Documents\n\n- Identification\n- Income statement\n\n' + 'Footer. '*300)
    eligibility, = read(page, 'Approved programme recipients')
    application, = read(page, 'No separate application')
    assert eligibility.complete and application.complete
    assert 'Eligibility' in eligibility.content + eligibility.heading_context
    assert 'How To Apply' in application.content + application.heading_context
    assert 'How To Apply' not in eligibility.content
    assert 'Required Documents' not in application.content
