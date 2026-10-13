use holdem::{evaluate, parse_card, EquityTable, HandClass, NUM_CLASSES, TOTAL_COMBOS};

fn rank_of(s: &str) -> u32 {
    let cards: Vec<u8> = s
        .split_whitespace()
        .map(|c| parse_card(c).unwrap())
        .collect();
    evaluate(&cards)
}

#[test]
fn hand_categories_are_ordered() {
    let ladder = [
        "2c 4d 6h 8s Tc Jd Kh", // 高牌
        "2c 2d 6h 8s Tc Jd Kh", // 一对
        "2c 2d 6h 6s Tc Jd Kh", // 两对
        "2c 2d 2h 8s Tc Jd Kh", // 三条
        "Ac 2d 3h 4s 5c Jd Kh", // 最小顺子
        "9c Td Jh Qs Kc 2d 3h", // 顺子
        "2h 4h 6h 8h Th Jd Kc", // 同花
        "2c 2d 2h 8s 8c Jd Kh", // 葫芦
        "2c 2d 2h 2s Tc Jd Kh", // 四条
        "Ah 2h 3h 4h 5h Jd Kc", // 最小同花顺
        "Th Jh Qh Kh Ah 2d 3c", // 皇家同花顺
    ];
    for pair in ladder.windows(2) {
        assert!(
            rank_of(pair[0]) < rank_of(pair[1]),
            "{} 应小于 {}",
            pair[0],
            pair[1]
        );
    }
}

#[test]
fn kickers_and_special_cases() {
    // 同样一对 A，踢脚大的赢。
    assert!(rank_of("Ac Ad Kh 9s 7c 4d 2h") > rank_of("Ac Ad Qh 9s 7c 4d 2h"));
    // 只取最好的五张：第六、七张不影响结果。
    assert_eq!(
        rank_of("Ac Ad Kh Qs Jc 4d 2h"),
        rank_of("Ac Ad Kh Qs Jc 5d 3h")
    );
    // 两组三条组成葫芦，取大的三条。
    assert!(rank_of("Kc Kd Kh 3s 3c 3d 2h") > rank_of("Qc Qd Qh As Ac 3d 2h"));
    // 三对时取最大的两对，剩下的最大牌做踢脚。
    assert_eq!(
        rank_of("Ac Ad Kh Ks 2c 2d Qh"),
        rank_of("Ac Ad Kh Ks 3c 3d Qh")
    );
    // 六张同花取最大的五张。
    assert!(rank_of("Ah Kh 9h 7h 5h 3h 2c") > rank_of("Ah Kh 9h 7h 4h 3h 2c"));
}

#[test]
fn hand_classes_cover_every_combo() {
    let total: usize = HandClass::all().map(|h| h.num_combos()).sum();
    assert_eq!(total, TOTAL_COMBOS);
    assert_eq!(HandClass::all().count(), NUM_CLASSES);
    for h in HandClass::all() {
        assert_eq!(h.combos().len(), h.num_combos());
        for [a, b] in h.combos() {
            assert_eq!(HandClass::of_cards(a, b), h);
            assert_eq!(HandClass::of_cards(b, a), h);
        }
        assert_eq!(HandClass::from_name(&h.name()), Some(h));
    }
    assert_eq!(HandClass::from_name("AA").unwrap().index(), 0);
    assert_eq!(HandClass::from_name("AKs").unwrap().index(), 1);
    assert_eq!(HandClass::from_name("AKo").unwrap().index(), 13);
}

#[test]
fn shipped_equity_table_matches_known_matchups() {
    let file = std::fs::File::open(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../data/equity_hu_169.bin"
    ))
    .expect("缺少 data/equity_hu_169.bin，用 gen-equity 生成");
    let table = EquityTable::read_from(std::io::BufReader::new(file)).unwrap();
    let h = |s| HandClass::from_name(s).unwrap();
    // 公认的全下胜率，允许 1 个百分点的误差。
    let known = [
        ("AA", "KK", 0.819),
        ("AKs", "QQ", 0.460),
        ("AKo", "QQ", 0.431),
        ("AKo", "22", 0.473),
        ("72o", "AA", 0.119),
        ("JTs", "AKo", 0.411),
    ];
    for (a, b, eq) in known {
        let got = table.get(h(a), h(b));
        assert!((got - eq).abs() < 0.01, "{a} 对 {b}：{got}，应约为 {eq}");
        assert!((got + table.get(h(b), h(a)) - 1.0).abs() < 1e-6);
    }
}
