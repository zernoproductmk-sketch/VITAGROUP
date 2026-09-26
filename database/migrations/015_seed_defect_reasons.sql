-- Seed standard QC defect reasons used in the production pilot.

INSERT INTO defect_reasons (code, category, name, is_active) VALUES
('QC_PRINT_SHIFT',        'Печать',              'Смещение печати', true),
('QC_BAD_GLUE',           'Склейка',             'Непроклей / плохая склейка', true),
('QC_BAG_TEAR',           'Механический дефект', 'Разрыв пакета', true),
('QC_BAG_DEFORMATION',    'Геометрия',           'Деформация пакета', true),
('QC_SIZE_MISMATCH',      'Геометрия',           'Несоответствие размеров', true),
('QC_HANDLE_DAMAGE',      'Ручка',               'Повреждение ручки', true),
('QC_BAD_DIE_CUT',        'Высечка',             'Неправильная высечка', true),
('QC_DIRT_STAINS',        'Качество поверхности','Загрязнение / пятна', true),
('QC_POOR_PRINT',         'Печать',              'Некачественная печать', true),
('QC_BAD_ASSEMBLY',       'Сборка',              'Неправильная сборка', true),
('QC_PACKING_DAMAGE',     'Упаковка',            'Повреждение при упаковке', true)
ON CONFLICT (code) DO UPDATE SET
    category = EXCLUDED.category,
    name = EXCLUDED.name,
    is_active = true;
