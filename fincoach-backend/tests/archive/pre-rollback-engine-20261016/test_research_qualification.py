from app.rag.research_windows import qualification_window


def test_heading_just_before_window_is_retained_within_bounds():
    page = '# Foreign spouse\nPassport and visa copies are required.\n\n# Adopted children\nProvide an adoption certificate.'
    text, context = qualification_window(page, 'Passport and visa copies are required.')
    assert 'Foreign spouse' in context
    assert len(text) + len(context) <= 1800
    assert context in page


def test_flattened_page_keeps_literal_neighbor_and_no_invented_heading():
    page = 'For adopted children: Provide an adoption certificate. For citizens: MyKad copy.'
    text, context = qualification_window(page, 'Provide an adoption certificate.')
    assert 'For adopted children:' in context and context in page
    assert text in page
