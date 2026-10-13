use holdem::{Card, HandClass, NUM_CLASSES};
use postflop_solver::Range;

/// 按 169 类起手牌的权重建范围，同一类的每个组合权重相同。
/// 权重会截到 0 到 1 之间；和公共牌冲突的组合由求解器自己剔除。
pub fn range_from_classes(weights: &[f64]) -> Range {
    assert_eq!(weights.len(), NUM_CLASSES);
    let mut range = Range::new();
    for class in HandClass::all() {
        let w = weights[class.index()].clamp(0.0, 1.0) as f32;
        for [a, b] in class.combos() {
            range.set_weight_by_cards(a, b, w);
        }
    }
    range
}

/// 按具体组合的权重建范围。
pub fn range_from_combos(combos: &[([Card; 2], f32)]) -> Range {
    let mut range = Range::new();
    for &([a, b], w) in combos {
        range.set_weight_by_cards(a, b, w.clamp(0.0, 1.0));
    }
    range
}
