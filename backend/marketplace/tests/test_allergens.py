import pytest


@pytest.mark.django_db
class TestAllergenInfo:
    """
    TC-015: allergen info is captured, defaulted, and returned by the API.
    The customer-facing display itself (badge colour/prominence on the
    catalogue page, before add-to-basket) was verified manually in the
    browser rather than here — see the "(TC-015)" commit and screenshots
    from that testing pass.
    """

    def test_blank_allergen_info_defaults_to_declared_text(self, api_client, producer_user, category):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'No Allergen Product', 'price': '1.00',
            'unit': 'kg', 'allergen_info': '',
        }, format='json')
        assert resp.status_code == 201
        assert resp.json()['allergen_info'] == 'No common allergens declared.'

    def test_explicit_allergen_info_preserved(self, api_client, producer_user, category):
        api_client.force_authenticate(user=producer_user.user)
        resp = api_client.post('/api/products/', {
            'category': category.id, 'name': 'Walnut Bread', 'price': '3.00',
            'unit': 'unit', 'allergen_info': 'Contains nuts, gluten',
        }, format='json')
        assert resp.json()['allergen_info'] == 'Contains nuts, gluten'

    def test_allergen_info_present_in_catalogue_response(self, api_client, product):
        resp = api_client.get('/api/products/')
        data = next(p for p in resp.json() if p['name'] == product.name)
        assert 'allergen_info' in data
