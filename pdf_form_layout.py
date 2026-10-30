"""Field rectangles in PDF points, measured against the unchanged AMB originals."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = {
    'new_account': ROOT / 'AMB ACCOUNT APPLICATION FORM (carlos lennix).pdf',
    'information_change': ROOT / 'AMB  Change or Added Information Request Form (carloslennix@gmail.com).pdf',
}


def field(key, page, x0, y0, x1, y1, **options):
    return dict(key=key, page=page, rect=[x0, y0, x1, y1], **options)


ACCOUNT = [
    field('company_name',0,177,219,381,231), field('business_start_date',0,510,219,587,231),
    field('trade_name',0,145,237,587,249),
    field('business_address',0,145,255,412,267), field('business_unit',0,528,255,587,267),
    field('business_city',0,69,273,183,285), field('business_state',0,285,273,369,285),
    field('business_postal_code',0,505,273,587,285),
    field('business_phone',0,145,291,345,303), field('business_fax',0,462,291,587,303),
    field('business_email',0,85,309,345,321), field('preferred_language',0,490,309,587,321),
    field('shipping_address',0,139,327,587,339),
    field('shipping_city',0,73,363,183,375), field('shipping_state',0,285,363,369,375),
    field('shipping_postal_code',0,505,363,587,375),
    field('lease_holder',0,325,381,587,393),
    field('tax_id',0,95,418,164,430), field('resale_tax_id',0,258,418,332,430),
    field('jbt_id',0,378,418,447,430), field('dnb_number',0,487,418,587,430),
    field('first_name',0,151,447,345,459), field('last_name',0,418,447,587,459),
    field('ssn',0,60,476,260,488), field('license_number',0,370,476,472,488),
    field('date_of_birth',0,518,476,587,488),
    field('home_address',0,119,495,445,507), field('home_unit',0,526,495,587,507),
    field('home_city',0,69,513,171,525), field('home_state',0,271,513,350,525),
    field('home_postal_code',0,485,513,587,525),
    field('home_phone',0,101,532,314,544), field('cell_phone',0,357,532,587,544),
    field('spouse_first_name',0,110,550,345,562), field('spouse_last_name',0,418,550,587,562),
    field('spouse_ssn',0,60,579,179,591), field('spouse_license_number',0,289,579,360,591),
    field('spouse_passport_number',0,529,579,587,591),
    *[field(f'buyer_{i}',0,55,y,587,y+12) for i,y in enumerate((615,630,645),1)],
    field('certificate_number',0,109,733,251,745), field('certificate_state',0,296,733,369,745),
    *[field(f'trade_{i}_{key}',1,x,y,x1,y+12)
      for i,y in enumerate((64,81,98,115),1)
      for key,x,x1 in [('company',119,235),('contact',310,378),('email_fax',432,587)]],
    *[field(f'personal_{i}_{key}',1,x,y,x1,y+12)
      for i,y in enumerate((153,170,187),1)
      for key,x,x1 in [('name',44,337),('phone',409,587)]],
    field('bank_name',1,100,226,297,238), field('bank_officer',1,448,226,587,238),
    field('bank_address',1,86,243,587,255), field('bank_phone',1,90,260,350,272),
    field('bank_account_number',1,425,260,587,272), field('bank_account_name',1,137,277,360,289),
    field('bank_opening_date',1,450,277,587,289), field('bank_authorization_date',1,448,322,587,334),
    field('prepared_date',1,488,497,587,509),
    field('principal_print_name',1,101,516,418,528), field('principal_title',1,474,516,587,528),
    field('second_print_name',1,110,553,406,565), field('second_title',1,460,553,587,565),
    field('date_received',1,119,648,350,660), field('jbt_rating',1,448,648,587,660),
    field('credit_terms',1,114,665,587,677), field('credit_limit',1,110,682,587,694),
    field('discount_special',1,222,699,306,711), field('discount_regular',1,372,699,587,711),
    field('date_approved',1,120,716,350,728), field('approved_by',1,448,716,587,728),
    field('sales_associate',1,172,733,587,745),
]
for value,x in [('private corp',29),('partnership',138),('individual',247),('other',355)]:
    ACCOUNT.append(field('entity_type',0,x,199,x+10,209, type='choice', value=value))
for value,x in [('residential',195),('commercial',304)]:
    ACCOUNT.append(field('shipping_type',0,x,342,x+10,352,type='choice',value=value))
for key,x in [('copy_driver_license',110),('copy_sales_tax_permit',272),('copy_lease_agreement',434)]:
    ACCOUNT.append(field(key,1,x,591,x+7,598,type='checkbox'))

CHANGE = [
    field('account_number',0,188,216,587,228),
    field('first_name',0,188,235,361,247), field('last_name',0,390,235,587,247),
    field('signed_date',0,476,549,587,562),
    field('credit_terms',0,188,625,587,638), field('credit_limit',0,188,649,587,662),
    field('discount_special',0,289,672,386,685), field('discount_regular',0,488,672,587,685),
    field('approved_by',0,26,710,159,723), field('updated_by',0,243,710,401,723),
    field('updated_date',0,477,710,587,723),
]
for prefix,ys in [('old_', (308,325,353,369,388)), ('new_', (423,442,472,491,510))]:
    company,trade,address,city,phone=ys
    CHANGE.extend([
        field(prefix+'company_name',0,188,company,442,company+12),
        field(prefix+'registration_state',0,517,company,587,company+12),
        field(prefix+'trade_name',0,188,trade,587,trade+12),
        field(prefix+'physical_address',0,188,address,402,address+12),
        field(prefix+'physical_unit',0,522,address,587,address+12),
        field(prefix+'physical_city',0,85,city,211,city+12),
        field(prefix+'physical_state',0,278,city,399,city+12),
        field(prefix+'physical_postal_code',0,477,city,587,city+12),
        field(prefix+'business_phone',0,121,phone,231,phone+12),
        field(prefix+'business_fax',0,287,phone,375,phone+12),
        field(prefix+'business_email',0,423,phone,587,phone+12),
    ])
for value,x in [('private corp',104),('partnership',250),('individual',346),('other',448)]:
    CHANGE.append(field('entity_type',0,x,268,x+8,276,type='choice',value=value))

LAYOUTS = {'new_account': ACCOUNT, 'information_change': CHANGE}
