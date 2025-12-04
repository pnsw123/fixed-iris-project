#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tribe Brain Builder
Creates a comprehensive database of Arab tribes for the AntiGravity app
Source: موسوعة القبائل العربية - محمد سليمان الطيب
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set


def create_tribe_database():
    """Create comprehensive database of Arab tribes with clean Arabic text"""
    
    tribes = {}
    
    # ===========================================
    # MAJOR TRIBAL CONFEDERATIONS (القبائل الكبرى)
    # ===========================================
    
    # 1. عنزة - One of the largest Arab tribal confederations
    tribes["عنزة"] = {
        "name": "عنزة",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من أكبر القبائل العربية",
        "subfamilies": [
            "الرولة", "الفدعان", "العمارات", "السبعة", "ولد علي",
            "الحسنة", "المنابهة", "البجايدة", "الجلاس", "بني وهب",
            "ضنا عبيد", "ضنا بشر", "ضنا مسلم", "آل جعفر", "الأشاجعة",
            "المصاليخ", "السلقا", "الدهامشة", "الرماح", "الشراعبة"
        ]
    }
    
    # 2. شمر - Major northern Arabian tribe
    tribes["شمر"] = {
        "name": "شمر",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من كبرى قبائل شمال الجزيرة العربية",
        "subfamilies": [
            "عبدة", "الأسلم", "زوبع", "سنجارة", "الصايح",
            "آل جربا", "آل علي", "طيء", "الغفيلة", "الصلتة",
            "الزميل", "الفداغة", "آل ثابت", "آل شمروخ", "المسعود"
        ]
    }
    
    # 3. قحطان - Major southern Arabian confederation
    tribes["قحطان"] = {
        "name": "قحطان",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من أعرق القبائل العربية",
        "subfamilies": [
            "سنحان", "الحباب", "الجحادر", "شريف", "عبيدة",
            "رفيدة", "بني بشر", "بني هاجر", "آل عاصم", "آل سريع",
            "آل الجمل", "وادعة", "آل عمر", "آل سعد", "آل مسعود"
        ]
    }
    
    # 4. حرب - Major Hejazi tribe
    tribes["حرب"] = {
        "name": "حرب",
        "type": "main_tribe",
        "origin": "خولانية قحطانية",
        "description": "من أكبر قبائل الحجاز",
        "subfamilies": [
            "بني سالم", "مسروح", "بني عمرو", "بني علي", "الصواعد",
            "زبيد", "بني السفر", "بني عوف", "الأحامدة", "المراوحة",
            "ولد محمد", "الفردة", "البيضان", "السهلة", "الحوازم",
            "الجبور", "المطارفة", "بني لقيان", "صبح", "عوف", "الغبان"
        ]
    }
    
    # 5. عتيبة - Major central Arabian tribe
    tribes["عتيبة"] = {
        "name": "عتيبة",
        "type": "main_tribe",
        "origin": "هوازنية عدنانية",
        "description": "من أكبر قبائل نجد والحجاز",
        "subfamilies": [
            "برقا", "روق", "بني سعد", "النفعة", "الدعاجين",
            "الحفاة", "الحماميد", "المقطة", "الغبيات", "طلحة",
            "ذوي ثبيت", "المراشدة", "الأساعدة", "العصمة", "الشيابين",
            "الحناتيش", "العضيان", "ذوي عطية", "الدغالبة", "الثبتة"
        ]
    }
    
    # 6. مطير - Major central Arabian tribe
    tribes["مطير"] = {
        "name": "مطير",
        "type": "main_tribe",
        "origin": "غطفانية عدنانية",
        "description": "من كبرى قبائل نجد",
        "subfamilies": [
            "بني عبدالله", "علوى", "برية", "الدواسر", "واصل",
            "الحبالين", "الشلالحة", "الجبلان", "الهويملات", "المحينات",
            "ذوي عون", "الغياثات", "الجميشات", "السميطات", "الأصافرة"
        ]
    }
    
    # 7. الدواسر - Major central/southern Arabian tribe
    tribes["الدواسر"] = {
        "name": "الدواسر",
        "type": "main_tribe",
        "origin": "تغلبية وقحطانية",
        "description": "من كبرى قبائل نجد",
        "subfamilies": [
            "آل زايد", "آل صهيب", "تغلب", "آل جعفر", "البدارين",
            "الخييلات", "الحقبان", "الرجبان", "الغييثات", "المخاريم",
            "الشرافا", "العمور", "آل حسن", "آل حماد", "الفراهيد"
        ]
    }
    
    # 8. بني تميم - Ancient and influential Arabian tribe
    tribes["بني تميم"] = {
        "name": "بني تميم",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من أعرق القبائل العدنانية",
        "subfamilies": [
            "الوهبة", "آل ماضي", "آل مقبل", "الحراقيص", "العوازم",
            "بني سعد", "العناقر", "الحبشان", "المجايشة", "المشاعيب",
            "النواصر", "الرزنان", "اليحيى", "الجليدان", "الحقيل"
        ]
    }
    
    # 9. السبيعي / سبيع - Central Arabian tribe
    tribes["سبيع"] = {
        "name": "سبيع",
        "type": "main_tribe",
        "origin": "عامرية هوازنية",
        "description": "من قبائل نجد العريقة",
        "subfamilies": [
            "بني عامر", "آل عمير", "الأعلى", "الردادة", "الجمعان",
            "السواقين", "المدارية", "الغدافين", "آل محمد", "الغلفان"
        ]
    }
    
    # 10. بني خالد - Eastern Arabian tribe
    tribes["بني خالد"] = {
        "name": "بني خالد",
        "type": "main_tribe",
        "origin": "طائية / ربعية",
        "description": "من كبرى قبائل شرق الجزيرة",
        "subfamilies": [
            "الجبور", "الدعوم", "آل حميد", "آل عريعر", "المهاشير",
            "العوازم", "آل صبيح", "الصبيحات", "المسالمة", "الجبارات"
        ]
    }
    
    # 11. بلي - Hejazi tribe
    tribes["بلي"] = {
        "name": "بلي",
        "type": "main_tribe",
        "origin": "قضاعية قحطانية",
        "description": "من قبائل الحجاز",
        "subfamilies": [
            "الفقرا", "المهادلة", "المواهيب", "الجرفة", "الحمر",
            "العقايلة", "الفحاطنة", "المعاقلة", "الجهمة", "زبالة"
        ]
    }
    
    # 12. جهينة - Major Hejazi tribe
    tribes["جهينة"] = {
        "name": "جهينة",
        "type": "main_tribe",
        "origin": "قضاعية قحطانية",
        "description": "من أكبر قبائل الحجاز",
        "subfamilies": [
            "بني إبراهيم", "بني مالك", "الحصينات", "ذبيان", "موسى",
            "الحمدة", "السنينات", "العوامرة", "القضاة", "المحايا",
            "الربعية", "الفوايدة", "العرف", "السميرات", "الشنابرة"
        ]
    }
    
    # 13. الحويطات - Northern Hejazi tribe
    tribes["الحويطات"] = {
        "name": "الحويطات",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من قبائل شمال الحجاز",
        "subfamilies": [
            "علوان", "عمران", "السليمانيين", "الجرافين", "التياها",
            "الزلابية", "المراعين", "السويلميين", "الفرعان", "الطقيقات",
            "المساعيد", "العميرات", "الفحيلات", "النجادات", "الجعافرة"
        ]
    }
    
    # 14. العجمان - Eastern Arabian tribe
    tribes["العجمان"] = {
        "name": "العجمان",
        "type": "main_tribe",
        "origin": "يامية همدانية",
        "description": "من كبرى قبائل شرق الجزيرة",
        "subfamilies": [
            "آل حبيش", "آل سفران", "آل محمد", "آل شامر", "آل ناصر",
            "آل هتلان", "آل مرة", "آل حارث", "آل علي", "آل سليمان"
        ]
    }
    
    # 15. يام - Southern/eastern Arabian tribe
    tribes["يام"] = {
        "name": "يام",
        "type": "main_tribe",
        "origin": "همدانية قحطانية",
        "description": "من قبائل نجران",
        "subfamilies": [
            "آل فاطمة", "دهم", "مران", "آل سالم", "آل عجمان",
            "آل مرة", "آل منصور", "آل مسفر", "آل خضير", "آل جبران"
        ]
    }
    
    # 16. سليم / بني سليم - Historic Arabian tribe
    tribes["بني سليم"] = {
        "name": "بني سليم",
        "type": "main_tribe",
        "origin": "قيسية عدنانية",
        "description": "من القبائل العدنانية الكبرى",
        "subfamilies": [
            "الشرارات", "الحميان", "العوازم", "الأحامد", "الصلبة",
            "الدرعان", "بني رشيد", "المقيلة", "الطوال", "الخيالات"
        ]
    }
    
    # 17. الظفير - Central/Eastern Arabian tribe
    tribes["الظفير"] = {
        "name": "الظفير",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من قبائل الكويت والجزيرة",
        "subfamilies": [
            "آل محمد", "الصمدة", "السويط", "البطين", "العويمرية",
            "الحمام", "السعيد", "البراك", "العدوان", "الغنايم"
        ]
    }
    
    # 18. زهران - Southern Hejazi tribe
    tribes["زهران"] = {
        "name": "زهران",
        "type": "main_tribe",
        "origin": "أزدية قحطانية",
        "description": "من قبائل جنوب الحجاز",
        "subfamilies": [
            "دوس", "أحمد", "الحياري", "بني عمر", "آل مسعود",
            "بني جندب", "بني سليم", "بني بكر", "بني فهم", "بني هلال"
        ]
    }
    
    # 19. غامد - Southern Hejazi tribe
    tribes["غامد"] = {
        "name": "غامد",
        "type": "main_tribe",
        "origin": "أزدية قحطانية",
        "description": "من قبائل جنوب الحجاز",
        "subfamilies": [
            "بني عبدالله", "بني ظبيان", "بالطفيل", "بني كبير", "آل سباق",
            "بالأسمر", "بني حرير", "بالأحمر", "بني عامر", "بالشهم"
        ]
    }
    
    # 20. بني شهر - Southern tribe
    tribes["بني شهر"] = {
        "name": "بني شهر",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من قبائل عسير",
        "subfamilies": [
            "الشنفرة", "بني قيس", "التهم", "آل المعافا", "بني لام",
            "الغيلان", "آل العلاء", "آل عمير", "آل جريب", "آل جمعة"
        ]
    }
    
    # 21. بني حرب - (Different from حرب)
    tribes["بني حرب"] = {
        "name": "بني حرب",
        "type": "main_tribe",
        "origin": "عدنانية",
        "subfamilies": [
            "آل مرير", "آل مضواح", "بني الأسمر", "آل خيرة"
        ]
    }
    
    # 22. عسير - Southern tribes
    tribes["عسير"] = {
        "name": "عسير",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من قبائل جنوب المملكة",
        "subfamilies": [
            "بني مغيد", "ربيعة ورفيدة", "علكم", "بني مالك", "آل موسى",
            "رجال الحجر", "بني شهر", "بللسمر", "بللحمر", "النماص"
        ]
    }
    
    # 23. خثعم - Southern tribe
    tribes["خثعم"] = {
        "name": "خثعم",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من قبائل جنوب المملكة",
        "subfamilies": [
            "بني واهب", "شهران", "أكلب", "الحميس", "ناهس",
            "كود", "عقيدة", "أصحاب", "بني يزيد", "بني جريب"
        ]
    }
    
    # 24. شهران - Southern tribe
    tribes["شهران"] = {
        "name": "شهران",
        "type": "main_tribe",
        "origin": "خثعمية قحطانية",
        "description": "من قبائل جنوب المملكة",
        "subfamilies": [
            "بني الأسمر", "بني بكر", "بني مالك", "ناهس", "بني منبح",
            "الشعف", "آل جبر", "آل عيفة", "آل سرحان", "آل معمر"
        ]
    }
    
    # 25. النعيم - Gulf tribe
    tribes["النعيم"] = {
        "name": "النعيم",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من قبائل الخليج",
        "subfamilies": [
            "آل بوخريبان", "آل بوشامس", "الخواطر", "آل مهيرة", "آل علي",
            "السودان", "آل بوفلاسة", "الكبسة", "آل حمودة", "المناصير"
        ]
    }
    
    # 26. بني ياس - UAE tribe
    tribes["بني ياس"] = {
        "name": "بني ياس",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "أكبر قبائل الإمارات",
        "subfamilies": [
            "آل نهيان", "آل مكتوم", "الرميثات", "آل بوفلاسة", "السودان",
            "المرر", "الهوامل", "القبيسات", "البوحمير", "المزاريع",
            "البوالمهاري", "الحوامل", "المشاغين", "القمزان", "السبايس"
        ]
    }
    
    # 27. الرشايدة - Nomadic Arabian tribe
    tribes["الرشايدة"] = {
        "name": "الرشايدة",
        "type": "main_tribe",
        "origin": "عبسية عدنانية",
        "description": "قبيلة بدوية منتشرة",
        "subfamilies": [
            "البراعصة", "الزنيمات", "البراهمة", "الزويدات", "العونة",
            "الحجايجة", "الغوانمة", "البريكات", "الرفيعات", "الشراقوة"
        ]
    }
    
    # 28. بني رشيد - Hejazi/Najdi tribe
    tribes["بني رشيد"] = {
        "name": "بني رشيد",
        "type": "main_tribe",
        "origin": "عبسية غطفانية",
        "description": "من قبائل الحجاز ونجد",
        "subfamilies": [
            "الضباعين", "الحمامدة", "الروسان", "المسنّد", "الدهالكة",
            "الرماح", "العجلة", "المطارفة", "الفداغة", "الصقور"
        ]
    }
    
    # 29. السرحان - Northern tribe
    tribes["السرحان"] = {
        "name": "السرحان",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من قبائل شمال الجزيرة",
        "subfamilies": [
            "الراشد", "الدلابحة", "الغوارنة", "الذيابات", "المصطفى",
            "الحمدان", "الشرفات", "الخطاطبة", "الحماد", "العبيد"
        ]
    }
    
    # 30. الشرارات - Northern Arabian tribe
    tribes["الشرارات"] = {
        "name": "الشرارات",
        "type": "main_tribe",
        "origin": "كلبية قضاعية",
        "description": "من قبائل شمال المملكة",
        "subfamilies": [
            "الضباعين", "الحلسة", "الحمامدة", "الصبيحات", "الفليحان",
            "الزميل", "الدلمة", "العزام", "الغنانيم", "الغبين"
        ]
    }
    
    # 31. عنيزة - Branch related to عنزة
    tribes["عنيزة"] = {
        "name": "عنيزة",
        "type": "main_tribe",
        "origin": "عدنانية",
        "subfamilies": [
            "آل سليم", "العساكر", "البسام", "الصالح", "المحمد"
        ]
    }
    
    # 32. بني هاجر - Southern/Gulf tribe
    tribes["بني هاجر"] = {
        "name": "بني هاجر",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من قبائل قحطان",
        "subfamilies": [
            "آل محمد", "المخضبة", "شريف", "آل كليب", "آل سعد",
            "السحمة", "الشملان", "آل سالم", "آل مسفر", "الحمادين"
        ]
    }
    
    # 33. آل مرة - Eastern Arabian tribe
    tribes["آل مرة"] = {
        "name": "آل مرة",
        "type": "main_tribe",
        "origin": "يامية همدانية",
        "description": "من قبائل شرق الجزيرة",
        "subfamilies": [
            "الغفران", "الجرابعة", "الفهيدة", "الشوامين", "آل علي",
            "آل شامر", "الطويرات", "آل عامر", "البحابحة", "المعاضيد"
        ]
    }
    
    # 34. المناصير - Gulf tribe
    tribes["المناصير"] = {
        "name": "المناصير",
        "type": "main_tribe",
        "origin": "أزدية",
        "description": "من قبائل الخليج",
        "subfamilies": [
            "آل بوريش", "آل بالوي", "البوشعر", "المحاربة", "العبادلة",
            "السهول", "الطنيجات", "آل قوقة", "الجوابر", "المزايدة"
        ]
    }
    
    # 35. الكواهلة - Sudanese/Arabian tribe
    tribes["الكواهلة"] = {
        "name": "الكواهلة",
        "type": "main_tribe",
        "origin": "زبيدية قحطانية",
        "description": "من القبائل العربية في السودان",
        "subfamilies": [
            "أولاد عقيل", "أولاد حامد", "أولاد عون", "الحسانية", "البشارية"
        ]
    }
    
    # 36. الجعليين - Major Sudanese tribe
    tribes["الجعليين"] = {
        "name": "الجعليين",
        "type": "main_tribe",
        "origin": "عباسية",
        "description": "من كبرى قبائل السودان",
        "subfamilies": [
            "الجموعية", "الشايقية", "الرباطاب", "الميرفاب", "المناصير",
            "الركابية", "البديرية", "الجوابرة", "العوامرة", "المجاذيب"
        ]
    }
    
    # 37. الشايقية - Sudanese tribe
    tribes["الشايقية"] = {
        "name": "الشايقية",
        "type": "main_tribe",
        "origin": "جعلية",
        "description": "من قبائل شمال السودان",
        "subfamilies": [
            "العدلاناب", "الحنكاب", "الأمراب", "السوراب", "الحاكماب",
            "التويراب", "الشمباتاب", "العمراب", "الفضلاب", "الكتياب"
        ]
    }
    
    # 38. كنانة - Ancient Arabian tribe
    tribes["كنانة"] = {
        "name": "كنانة",
        "type": "main_tribe",
        "origin": "مضرية عدنانية",
        "description": "من أعرق القبائل العدنانية",
        "subfamilies": [
            "بني الدئل", "بني عبد مناة", "بني مالك", "بني ملكان", "فراس",
            "النضر", "بني ليث", "بني ضمرة", "بني غفار", "بني جذيمة"
        ]
    }
    
    # 39. قريش - Prophet's tribe
    tribes["قريش"] = {
        "name": "قريش",
        "type": "main_tribe",
        "origin": "كنانية عدنانية",
        "description": "قبيلة النبي محمد صلى الله عليه وسلم",
        "subfamilies": [
            "بنو هاشم", "بنو أمية", "بنو مخزوم", "بنو عبد الدار", "بنو زهرة",
            "بنو تيم", "بنو عدي", "بنو سهم", "بنو جمح", "بنو أسد",
            "بنو نوفل", "بنو عبد شمس", "بنو المطلب", "بنو الحارث", "بنو عامر"
        ]
    }
    
    # 40. ثقيف - Historic Arabian tribe
    tribes["ثقيف"] = {
        "name": "ثقيف",
        "type": "main_tribe",
        "origin": "هوازنية قيسية",
        "description": "من قبائل الطائف العريقة",
        "subfamilies": [
            "بنو مالك", "الأحلاف", "بنو سعد", "بنو عوف", "بنو جشم"
        ]
    }
    
    # 41. هذيل - Hejazi tribe
    tribes["هذيل"] = {
        "name": "هذيل",
        "type": "main_tribe",
        "origin": "مضرية عدنانية",
        "description": "من قبائل الحجاز",
        "subfamilies": [
            "بني لحيان", "بني صاهلة", "بني سعد", "بني مسروح", "بني قرد",
            "الحرابية", "السواقين", "الرهوة", "النمور", "البقوم"
        ]
    }
    
    # 42. البقوم - Central Arabian tribe
    tribes["البقوم"] = {
        "name": "البقوم",
        "type": "main_tribe",
        "origin": "أزدية",
        "description": "من قبائل نجد",
        "subfamilies": [
            "آل عياد", "الأساعدة", "الجثاثين", "السلسة", "الشنابين",
            "الصملة", "العمامير", "القثمة", "المحاميد", "الوذانين"
        ]
    }
    
    # 43. سبأ - Ancient Yemeni
    tribes["سبأ"] = {
        "name": "سبأ",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من أعرق القبائل اليمنية",
        "subfamilies": [
            "حمير", "كهلان", "همدان", "مذحج", "كندة",
            "الأزد", "طيء", "لخم", "جذام", "عاملة"
        ]
    }
    
    # 44. همدان - Major Yemeni tribe
    tribes["همدان"] = {
        "name": "همدان",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من كبرى قبائل اليمن",
        "subfamilies": [
            "حاشد", "بكيل", "يام", "أرحب", "ذو رعين",
            "نهم", "شاكر", "وادعة", "مرهبة", "خارف"
        ]
    }
    
    # 45. مذحج - Yemeni tribal confederation
    tribes["مذحج"] = {
        "name": "مذحج",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "اتحاد قبلي يمني كبير",
        "subfamilies": [
            "عنس", "مراد", "زبيد", "سعد العشيرة", "النخع",
            "جنب", "صداء", "رهاء", "الحكم", "جعفي"
        ]
    }
    
    # 46. كندة - Ancient Arabian kingdom/tribe
    tribes["كندة"] = {
        "name": "كندة",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "مملكة وقبيلة عربية قديمة",
        "subfamilies": [
            "بنو معاوية", "السكون", "بنو الحارث", "السكاسك", "تجيب"
        ]
    }
    
    # 47. الأزد - Major Yemeni origin tribe
    tribes["الأزد"] = {
        "name": "الأزد",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من أكبر القبائل القحطانية",
        "subfamilies": [
            "الأوس", "الخزرج", "خزاعة", "غسان", "بارق",
            "دوس", "زهران", "غامد", "لهب", "شكر"
        ]
    }
    
    # 48. طيء - Major northern tribe
    tribes["طيء"] = {
        "name": "طيء",
        "type": "main_tribe",
        "origin": "قحطانية",
        "description": "من كبرى قبائل شمال الجزيرة",
        "subfamilies": [
            "بنو لام", "الغوث", "جديلة", "جرم", "نبهان",
            "سنبس", "ثعل", "بولان", "سلامان", "معن"
        ]
    }
    
    # 49. العوازم - Gulf/Najdi tribe
    tribes["العوازم"] = {
        "name": "العوازم",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من قبائل الخليج ونجد",
        "subfamilies": [
            "آل غانم", "آل عويد", "القماعين", "المصابحة", "الهدالين",
            "الزرافين", "الشرارات", "الجحادلة", "الوحاحدة", "الصقور"
        ]
    }
    
    # 50. بني صخر - Jordanian/Syrian tribe
    tribes["بني صخر"] = {
        "name": "بني صخر",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من كبرى قبائل الأردن وسوريا",
        "subfamilies": [
            "الطوقة", "الكعابنة", "الخرشان", "السلايطة",
            "الفايز", "الزبن", "الجبور", "الحجايا", "الدعجة"
        ]
    }
    
    # 51. الحويطات (duplicate but with more subfamilies)
    tribes["بني عطية"] = {
        "name": "بني عطية",
        "type": "main_tribe",
        "origin": "جذامية",
        "description": "من قبائل شمال الحجاز",
        "subfamilies": [
            "العليين", "الفريجات", "العمارين", "السعيديين", "الرموث",
            "الروالة", "الفقراء", "العطيات", "الرحيلات", "المعازة"
        ]
    }
    
    # 52. المساعيد - Northern tribe
    tribes["المساعيد"] = {
        "name": "المساعيد",
        "type": "main_tribe",
        "origin": "حربية",
        "description": "من قبائل الأردن والحجاز",
        "subfamilies": [
            "الحجايا", "العودات", "الحماد", "السبيلات", "البراهمة"
        ]
    }
    
    # 53. العمارات - Branch of Anizah
    tribes["العمارات"] = {
        "name": "العمارات",
        "type": "main_tribe",
        "origin": "عنزية عدنانية",
        "description": "من فروع قبيلة عنزة",
        "subfamilies": [
            "الجبل", "الدهامشة", "السلقا", "السويلمات", "الصقور"
        ]
    }
    
    # 54. الفضول - Central/Eastern tribe
    tribes["الفضول"] = {
        "name": "الفضول",
        "type": "main_tribe",
        "origin": "طائية لامية",
        "description": "من قبائل شرق الجزيرة",
        "subfamilies": [
            "آل كثير", "آل سنان", "آل فضل", "آل محمد", "الجعافرة",
            "النوامي", "السهول", "الفردان", "الوسامة", "المراغين"
        ]
    }
    
    # 55. السهول - Central Arabian tribe
    tribes["السهول"] = {
        "name": "السهول",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من قبائل نجد",
        "subfamilies": [
            "آل محمد", "الحزمان", "آل عويد", "آل عمر", "الفضلة"
        ]
    }
    
    # 56. بني زيد - Najdi tribe
    tribes["بني زيد"] = {
        "name": "بني زيد",
        "type": "main_tribe",
        "origin": "قضاعية",
        "description": "من قبائل نجد",
        "subfamilies": [
            "القراشة", "الجبرة", "العرينات", "المحامدة", "الحسكان"
        ]
    }
    
    # 57. بني عقيل - Eastern tribes
    tribes["بني عقيل"] = {
        "name": "بني عقيل",
        "type": "main_tribe",
        "origin": "عامرية عدنانية",
        "description": "من القبائل العدنانية",
        "subfamilies": [
            "عبادة", "خفاجة", "عقيل", "المنتفق", "بني كعب"
        ]
    }
    
    # 58. المنتفق - Iraqi tribe
    tribes["المنتفق"] = {
        "name": "المنتفق",
        "type": "main_tribe",
        "origin": "عقيلية عدنانية",
        "description": "من كبرى قبائل جنوب العراق",
        "subfamilies": [
            "آل سعدون", "الأجود", "بني مالك", "بني سعيد", "الشريفات",
            "الظوالم", "البدور", "آل صالح", "الغزي", "العبودة"
        ]
    }
    
    # 59. ربيعة - Ancient Arabian confederation
    tribes["ربيعة"] = {
        "name": "ربيعة",
        "type": "main_tribe",
        "origin": "عدنانية",
        "description": "من أعرق القبائل العدنانية",
        "subfamilies": [
            "بكر بن وائل", "تغلب", "عنزة", "عبد القيس", "بني حنيفة",
            "النمر", "ضبيعة", "شيبان", "عجل", "يشكر"
        ]
    }
    
    # 60. تغلب - Ancient Arabian tribe
    tribes["تغلب"] = {
        "name": "تغلب",
        "type": "main_tribe",
        "origin": "ربيعية عدنانية",
        "description": "من القبائل العدنانية العريقة",
        "subfamilies": [
            "بنو جشم", "بنو مالك", "بنو ثعلبة", "بنو عتاب", "بنو ذهل"
        ]
    }
    
    # 61. بكر بن وائل - Major Arabian tribe
    tribes["بكر بن وائل"] = {
        "name": "بكر بن وائل",
        "type": "main_tribe",
        "origin": "ربيعية عدنانية",
        "description": "من كبرى قبائل ربيعة",
        "subfamilies": [
            "شيبان", "عجل", "يشكر", "قيس بن ثعلبة", "ضبيعة",
            "تيم اللات", "ذهل", "قيس", "حنيفة", "عنزة"
        ]
    }
    
    # 62. Additional Egyptian/Libyan tribes
    tribes["أولاد علي"] = {
        "name": "أولاد علي",
        "type": "main_tribe",
        "origin": "سليمية",
        "description": "من قبائل مصر وليبيا",
        "subfamilies": [
            "أولاد علي الأبيض", "أولاد علي الأحمر", "السننة", "القنيشات", "الجميعات",
            "الحرابي", "العقاري", "السمالوس", "الشواعر", "العجارمة"
        ]
    }
    
    tribes["الجوازي"] = {
        "name": "الجوازي",
        "type": "main_tribe",
        "origin": "سليمية",
        "description": "من قبائل ليبيا",
        "subfamilies": [
            "المغاربة", "الصوالح", "الجمامعة", "الحسونة", "الزياينة"
        ]
    }
    
    tribes["المقارحة"] = {
        "name": "المقارحة",
        "type": "main_tribe",
        "origin": "هلالية",
        "description": "من قبائل ليبيا",
        "subfamilies": [
            "الجلالات", "العمائم", "القواسم", "الحنيوات", "الشلالفة"
        ]
    }
    
    # 63. Moroccan tribes
    tribes["بني هلال"] = {
        "name": "بني هلال",
        "type": "main_tribe",
        "origin": "عامرية هوازنية",
        "description": "من أشهر القبائل العربية المهاجرة",
        "subfamilies": [
            "زغبة", "رياح", "الأثبج", "جشم", "قرة",
            "عدي", "ربيعة", "زغبة", "عامر", "خلط"
        ]
    }
    
    # 64. Tunisian tribes
    tribes["الهمامة"] = {
        "name": "الهمامة",
        "type": "main_tribe",
        "origin": "سليمية",
        "description": "من قبائل تونس",
        "subfamilies": [
            "أولاد نصير", "أولاد عيار", "أولاد بوسعيد", "المثاليث", "أولاد محمد"
        ]
    }
    
    # 65. Mauritanian tribes
    tribes["حسان"] = {
        "name": "حسان",
        "type": "main_tribe",
        "origin": "معقلية يمنية",
        "description": "من قبائل موريتانيا",
        "subfamilies": [
            "المغافرة", "أولاد رزق", "أولاد دليم", "تكنة", "الركيبات"
        ]
    }
    
    # 66. Iraqi tribes
    tribes["شمر الجربا"] = {
        "name": "شمر الجربا",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من كبرى قبائل العراق",
        "subfamilies": [
            "الجربا", "الصايح", "زوبع", "سنجارة", "عبدة",
            "آل سلمان", "آل فارس", "الويسات", "الدغيرات", "البعيج"
        ]
    }
    
    tribes["الدليم"] = {
        "name": "الدليم",
        "type": "main_tribe",
        "origin": "زبيدية",
        "description": "من كبرى قبائل غرب العراق",
        "subfamilies": [
            "البوعساف", "الكرابلة", "البومحل", "البونمر", "البوعلوان",
            "البوفهد", "البوذياب", "البوعيسى", "البومراد", "البوجواري"
        ]
    }
    
    tribes["زبيد"] = {
        "name": "زبيد",
        "type": "main_tribe",
        "origin": "مذحجية قحطانية",
        "description": "من القبائل القحطانية الكبرى",
        "subfamilies": [
            "بني معروف", "العزة", "البوسلطان", "اللهيب", "العبيد",
            "الجنابيين", "العيثاويين", "السواعد", "الدعيج", "الجبور"
        ]
    }
    
    tribes["الجبور"] = {
        "name": "الجبور",
        "type": "main_tribe",
        "origin": "زبيدية",
        "description": "من كبرى قبائل العراق",
        "subfamilies": [
            "البومتيوت", "البورديني", "الغرير", "المعامرة", "الملحان",
            "البوشجاع", "البوخطاب", "الكرعاوي", "البورحمة", "البوعبدالله"
        ]
    }
    
    tribes["العبيد"] = {
        "name": "العبيد",
        "type": "main_tribe",
        "origin": "زبيدية",
        "description": "من قبائل العراق",
        "subfamilies": [
            "البوحمدان", "البوغانم", "البونجم", "الصالح", "البوكعيد",
            "البومنصور", "البورماح", "البوتمر", "البوجاسم", "البويوسف"
        ]
    }
    
    # 67. Palestinian/Jordanian tribes
    tribes["بني حسن"] = {
        "name": "بني حسن",
        "type": "main_tribe",
        "origin": "طائية",
        "description": "من قبائل الأردن وفلسطين",
        "subfamilies": [
            "الخوالدة", "الزيود", "العثامنة", "الخطاطبة", "العمايرة",
            "الهلسة", "المراشدة", "الخرابشة", "الدعجة", "الشرعة"
        ]
    }
    
    # 68. Gulf Emirates tribes
    tribes["آل نهيان"] = {
        "name": "آل نهيان",
        "type": "main_tribe",
        "origin": "بني ياس",
        "description": "الأسرة الحاكمة في أبوظبي",
        "subfamilies": [
            "آل بوفلاح", "آل محمد", "آل هزاع", "آل خليفة", "آل سيف"
        ]
    }
    
    tribes["آل مكتوم"] = {
        "name": "آل مكتوم",
        "type": "main_tribe",
        "origin": "بني ياس",
        "description": "الأسرة الحاكمة في دبي",
        "subfamilies": [
            "آل راشد", "آل سعيد", "آل حمدان", "آل محمد", "البوفلاسة"
        ]
    }
    
    tribes["آل ثاني"] = {
        "name": "آل ثاني",
        "type": "main_tribe",
        "origin": "بني تميم",
        "description": "الأسرة الحاكمة في قطر",
        "subfamilies": [
            "آل أحمد", "آل خالد", "آل محمد", "آل جاسم", "آل علي"
        ]
    }
    
    tribes["آل خليفة"] = {
        "name": "آل خليفة",
        "type": "main_tribe",
        "origin": "عتبية عنزية",
        "description": "الأسرة الحاكمة في البحرين",
        "subfamilies": [
            "آل أحمد", "آل محمد", "آل سلمان", "آل عبدالله", "آل حمد"
        ]
    }
    
    tribes["آل صباح"] = {
        "name": "آل صباح",
        "type": "main_tribe",
        "origin": "عتبية عنزية",
        "description": "الأسرة الحاكمة في الكويت",
        "subfamilies": [
            "آل جابر", "آل سالم", "آل أحمد", "آل صباح", "آل محمد"
        ]
    }
    
    # Add total count to each tribe
    for tribe_name, tribe_data in tribes.items():
        tribe_data["total_count"] = len(tribe_data.get("subfamilies", []))
    
    return tribes


def build_index(tribes):
    """Build reverse lookup index for fast searching"""
    index = {}
    
    for main_tribe, data in tribes.items():
        # Normalize name for search
        normalized_name = main_tribe.strip()
        
        # Add main tribe to index
        index[normalized_name] = {
            'is_main': True,
            'main_tribe': main_tribe,
            'path': [main_tribe],
            'type': 'main_tribe'
        }
        
        # Add common variations (with/without "بني", "بنو", "آل")
        for prefix in ["بني ", "بنو ", "آل "]:
            if main_tribe.startswith(prefix):
                base_name = main_tribe[len(prefix):]
                if base_name not in index:
                    index[base_name] = {
                        'is_main': False,
                        'main_tribe': main_tribe,
                        'path': [main_tribe],
                        'type': 'alias'
                    }
        
        # Add subfamilies to index
        for subfamily in data.get('subfamilies', []):
            normalized_sub = subfamily.strip()
            if normalized_sub and normalized_sub not in index:
                index[normalized_sub] = {
                    'is_main': False,
                    'main_tribe': main_tribe,
                    'path': [main_tribe, subfamily],
                    'type': 'subfamily'
                }
    
    return index


def main():
    print("🏛️  Building Tribe Brain Database...")
    print("=" * 50)
    
    # Create comprehensive tribe database
    tribes = create_tribe_database()
    
    # Build search index
    print("🔨 Building search index...")
    # ... (existing hardcoded tribes) ...
    
    # --- INTEGRATION START ---
    print("\n🔄 Running automated extraction from tribes.txt...")
    try:
        import subprocess
        
        # Process each input file
        # NOTE: tribes2_normalized.txt is the NFKC-normalized version of tribes2.txt
        # which converts Arabic presentation forms to standard characters
        input_files = ['tribes.txt', 'tribes2_normalized.txt']
        
        for filename in input_files:
            file_path = Path(__file__).parent.parent / filename
            if not file_path.exists():
                print(f"⚠️  Warning: {filename} not found, skipping.")
                continue
                
            print(f"\n🚀 Running extraction on {filename}...")
            
            # Run extraction script
            script_path = Path(__file__).parent / 'extract_tribes.py'
            try:
                result = subprocess.run(
                    [sys.executable, str(script_path), str(file_path)],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    check=True
                )
                
                # Parse output (stdout should be clean JSON now)
                try:
                    extracted_data = json.loads(result.stdout)
                    print(f"   Found {len(extracted_data)} tribes in {filename}")
                    
                    # Helper for normalization
                    def normalize_text(text):
                        import re
                        text = re.sub('[إأٱآا]', 'ا', text)
                        text = re.sub('ى', 'ي', text)
                        text = re.sub('ة', 'ه', text)
                        return text

                    # Merge data
                    for tribe_name, data in extracted_data.items():
                        # Normalize key
                        raw_key = tribe_name.strip()
                        key = raw_key
                        
                        # Check if exists (normalized)
                        norm_key = normalize_text(raw_key)
                        for existing_k in tribes:
                            if normalize_text(existing_k) == norm_key:
                                key = existing_k
                                break
                        parent_name = data.get('parent')
                        description = data.get('description', f"تم استخراجه آلياً من {filename}")
                        
                        # Strategy:
                        # 1. If parent exists in DB, add this tribe as a subfamily to the parent.
                        # 2. If tribe already exists in DB, update it.
                        # 3. Otherwise, add as new main tribe (with description).
                        
                        if parent_name:
                            # Try to find parent in existing tribes
                            for existing_tribe in tribes:
                                if existing_tribe in parent_name or parent_name in existing_tribe:
                                    # Found parent! Add as subfamily
                                    if key not in tribes[existing_tribe]['subfamilies']:
                                        tribes[existing_tribe]['subfamilies'].append(key)
                                        tribes[existing_tribe]['subfamilies'].sort()
                                    # We still want to add this tribe as a main entry if it has its own data
                                    break
                        
                        # Always add/update this tribe as a main entry if it was extracted as one
                        if key in tribes:
                            # Merge subfamilies
                            existing_subs = set(tribes[key]['subfamilies'])
                            new_subs = set(data['subfamilies'])
                            merged_subs = list(existing_subs.union(new_subs))
                            tribes[key]['subfamilies'] = sorted(merged_subs)
                            # Update description if it was default
                            if tribes[key]['description'].startswith("تم استخراجه"):
                                tribes[key]['description'] = description
                        else:
                            # Add new tribe
                            tribes[key] = {
                                "name": key,
                                "type": "main_tribe",
                                "origin": parent_name if parent_name else "غير محدد",
                                "description": description,
                                "subfamilies": sorted(data['subfamilies'])
                            }

                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON from {filename}: {e}")
                    
            except subprocess.CalledProcessError as e:
                print(f"❌ Extraction failed for {filename}: {e}")
                print(e.stderr)
                
    except Exception as e:
        print(f"❌ Error running extraction: {e}")
    # --- INTEGRATION END ---

    index = build_index(tribes)
    
    # Calculate statistics
    total_main = len(tribes)
    total_subfamilies = sum(len(t.get('subfamilies', [])) for t in tribes.values())
    total_entries = len(index)
    
    # Create the brain structure
    brain = {
        "tribes": tribes,
        "index": index,
        "metadata": {
            "total_main_tribes": total_main,
            "total_subfamilies": total_subfamilies,
            "total_entries": total_entries,
            "source": "موسوعة القبائل العربية - محمد سليمان الطيب",
            "author": "محمد سليمان الطيب",
            "generated": datetime.now().isoformat(),
            "version": "4.1-automated",
            "description": "Comprehensive database of major Arab tribes with automated extraction from source text"
        }
    }
    
    # Save to file
    output_path = Path(__file__).parent.parent / 'tribe_brain.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(brain, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Tribe Brain saved to: {output_path}")
    print(f"\n📊 Statistics:")
    print(f"   • Main Tribes: {total_main}")
    print(f"   • Total Subfamilies: {total_subfamilies}")
    print(f"   • Total Searchable Entries: {total_entries}")
    
    # Print tribe list (top 50 by size)
    print(f"\n📜 Top 50 Main Tribes by Size:")
    print("-" * 50)
    sorted_tribes = sorted(tribes.items(), key=lambda x: len(x[1].get('subfamilies', [])), reverse=True)
    for i, (tribe_name, tribe_data) in enumerate(sorted_tribes[:50], 1):
        subfamily_count = len(tribe_data.get('subfamilies', []))
        origin = tribe_data.get('origin', 'غير محدد')
        print(f"   {i:3}. {tribe_name} ({origin}) - {subfamily_count} subfamilies")


if __name__ == '__main__':
    main()
