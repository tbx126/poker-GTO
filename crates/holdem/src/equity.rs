use crate::cards::{Card, Deck};
use crate::eval::evaluate;
use crate::hands::{HandClass, NUM_CLASSES};
use std::io::{self, Read, Write};

/// SplitMix64，足够快，而且结果只取决于种子，方便复现。
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Rng {
        Rng(seed)
    }

    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    pub fn below(&mut self, n: usize) -> usize {
        (((self.next_u64() >> 32) * n as u64) >> 32) as usize
    }
}

const MAGIC: &[u8; 8] = b"EQ169v1\0";

/// 两人全下胜率表：`get(a, b)` 是 a 对 b 的胜率（平局算一半），
/// 对所有不冲突的具体组合和所有公共牌取平均。
pub struct EquityTable {
    values: Vec<f32>,
}

impl EquityTable {
    pub fn get(&self, a: HandClass, b: HandClass) -> f32 {
        self.values[a.index() * NUM_CLASSES + b.index()]
    }

    /// 按行展开的 169×169 矩阵。
    pub fn as_slice(&self) -> &[f32] {
        &self.values
    }

    /// 蒙特卡洛估算：每对起手牌抽 `samples` 次，标准误差约为 0.5 / sqrt(samples)。
    pub fn compute(samples: usize, threads: usize, seed: u64) -> EquityTable {
        let pairs: Vec<(HandClass, HandClass)> = HandClass::all()
            .flat_map(|a| {
                HandClass::all()
                    .filter(move |b| a.0 < b.0)
                    .map(move |b| (a, b))
            })
            .collect();
        let threads = threads.max(1);
        let chunk = pairs.len().div_ceil(threads);
        let results: Vec<(HandClass, HandClass, f32)> = std::thread::scope(|scope| {
            let handles: Vec<_> = pairs
                .chunks(chunk)
                .enumerate()
                .map(|(i, part)| {
                    scope.spawn(move || {
                        let mut rng =
                            Rng::new(seed ^ (i as u64).wrapping_mul(0xA24B_AED4_963E_E407));
                        part.iter()
                            .map(|&(a, b)| (a, b, sample_pair(a, b, samples, &mut rng)))
                            .collect::<Vec<_>>()
                    })
                })
                .collect();
            handles
                .into_iter()
                .flat_map(|h| h.join().expect("计算线程崩溃"))
                .collect()
        });

        let mut values = vec![0.5f32; NUM_CLASSES * NUM_CLASSES];
        for (a, b, eq) in results {
            values[a.index() * NUM_CLASSES + b.index()] = eq;
            values[b.index() * NUM_CLASSES + a.index()] = 1.0 - eq;
        }
        EquityTable { values }
    }

    pub fn write_to(&self, mut w: impl Write) -> io::Result<()> {
        w.write_all(MAGIC)?;
        for v in &self.values {
            w.write_all(&v.to_le_bytes())?;
        }
        Ok(())
    }

    pub fn read_from(mut r: impl Read) -> io::Result<EquityTable> {
        let mut magic = [0u8; 8];
        r.read_exact(&mut magic)?;
        if &magic != MAGIC {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "不是胜率表文件"));
        }
        let mut values = vec![0f32; NUM_CLASSES * NUM_CLASSES];
        let mut buf = [0u8; 4];
        for v in &mut values {
            r.read_exact(&mut buf)?;
            *v = f32::from_le_bytes(buf);
        }
        Ok(EquityTable { values })
    }
}

fn sample_pair(a: HandClass, b: HandClass, samples: usize, rng: &mut Rng) -> f32 {
    let (ca, cb) = (a.combos(), b.combos());
    let mut score = 0.0f64;
    let mut done = 0;
    while done < samples {
        let x = ca[rng.below(ca.len())];
        let y = cb[rng.below(cb.len())];
        if x.iter().any(|c| y.contains(c)) {
            continue;
        }
        let mut deck = Deck::default();
        let mut hand_a: [Card; 7] = [x[0], x[1], 0, 0, 0, 0, 0];
        let mut hand_b: [Card; 7] = [y[0], y[1], 0, 0, 0, 0, 0];
        for c in x.iter().chain(&y) {
            deck.take(*c);
        }
        let mut n = 2;
        while n < 7 {
            let c = rng.below(52) as Card;
            if !deck.contains(c) {
                deck.take(c);
                hand_a[n] = c;
                hand_b[n] = c;
                n += 1;
            }
        }
        let (ra, rb) = (evaluate(&hand_a), evaluate(&hand_b));
        score += match ra.cmp(&rb) {
            std::cmp::Ordering::Greater => 1.0,
            std::cmp::Ordering::Equal => 0.5,
            std::cmp::Ordering::Less => 0.0,
        };
        done += 1;
    }
    (score / samples as f64) as f32
}
