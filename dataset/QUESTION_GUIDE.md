# TDA Eval: Soru Yazım Kılavuzu

Şema sürümü: 1.0.0 · Veri seti sürümü: 0.1.0 (pilot) · Proje: TDA Eval

Bu kılavuz, `questions.jsonl` içine eklenecek her sorunun nasıl yazılacağını, nasıl puanlanacağını ve nasıl inceleneceğini tanımlar. Teknik tanımlar `question.schema.json` (alanlar ve kurallar) ile `categories.json` (kategoriler, metrikler, rubrikler, normalizasyon ve kısıt tanımları) dosyalarındadır; bu kılavuz onlarla çelişmemelidir ve tutarlılık testlerle denetlenir.

> **Pilot uyarısı.** v0.1.0 yaklaşık 100 sorudan oluşur (kategori başına 10). Bu boyut modelleri istatistiksel olarak güvenilir biçimde sıralamak için yeterli değildir. Sorular ve cevap anahtarları tamamen açıktır; test veri sızıntısı riski vardır. Gizli bir test seti ileride ayrı oluşturulacaktır.

## 1. Temel ilkeler

1. **Özgün veya lisansı net.** v0.1.0 soruları özgün yazılır (`source.type = "original"`). Üçüncü taraf içerik yalnızca lisansı doğrulanmış ve izinli lisans listesinde olan kaynaklardan alınır. Lisansı belirsiz kaynak kullanılmaz.
2. **Tek ve kontrol edilebilir cevap.** Nesnel sorunun bağımsız olarak doğrulanabilir tek bir cevabı olmalıdır.
3. **Uydurma gerçek yok.** Olgusal cevap anahtarı güvenilir bir kaynakla doğrulanır ve `references` alanına kaydedilir.
4. **Zamana duyarlı bilgiden kaçın.** Kaçınılamıyorsa `valid_as_of` yazılır.
5. **Eğitim verisiyle karıştırma.** Sınav kitabı, ders notu veya internetten kopyalama yapılmaz; sorular yeniden yazılır.
6. **Belirsizlik yok.** Soruyu bilen biri farklı bir doğru cevap bulabiliyorsa soru yeniden yazılır.
7. **Tarafsızlık.** Siyasi, dini veya tartışmalı konularda görüş sorulmaz; yalnızca doğrulanabilir olgular sorulur.

## 2. Kimlik, aralıklar ve test örnekleri

- `id` biçimi `<ÖNEK>-<3 hane>` (örn. `MAT-014`). Önekler: TLU, LOG, MAT, GKN, COD, IFL, GRM, RCP, CRW, FAC. Önek kategoriyle eşleşmelidir.
- **001–899: gerçek veri seti soruları. 900–999: yalnızca test örnekleri (fixture).** 9xx kimlikli bir madde `split: "fixture"` taşımak zorundadır; diğer maddeler `split: "pilot"` taşır. Fixture maddeleri `questions.jsonl` içine alınmaz; doğrulayıcı gerçek veri setinde fixture bulursa hata verir. Fixture maddeleri her zaman `reviewed: false` kalır.
- Bir `id` bir kez verilir; silinmez ve yeniden kullanılmaz. Sorunlu soru `status: "deprecated"` yapılır, nedeni `verification.notes` içine yazılır.
- Soru metni veya cevabı sonradan değişirse yeni `id` verilir, eski soru deprecated olur. Böylece eski sonuçlar yanıltıcı hâle gelmez.
- `added_in`, sorunun eklendiği veri seti sürümüdür (şu an `0.1.0`).

## 3. Lisans alanları

Üç ayrı lisans kavramı vardır ve karıştırılmaz:

| Alan | Neyin lisansı | Kim doldurur |
|---|---|---|
| Proje kodu lisansı (`categories.json` → `license_policy`) | TDA Eval yazılımı (Space deposu) | Proje, sabit: Apache-2.0 |
| `license` | Bu soru maddesinin veri setinde hangi lisansla dağıtıldığı | Her soruda zorunlu; `original` maddelerde Apache-2.0 olmak zorundadır |
| `source.license` | Üçüncü taraf kaynağın KENDİ lisansı | Yalnızca `third_party` ve `public_domain` maddelerde zorunlu; `original` maddede bulunamaz |

Üçüncü taraf maddelerde `source.name`, `source.url`, `source.license` ve `source.retrieved_date` zorunludur. `source.url` http(s) adresi olmalı ve kimlik bilgisi içermemelidir. Hem `license` hem `source.license`, `categories.json` içindeki `third_party_allowed_licenses` listesinde olmalıdır; liste dışı lisans reddedilir.

## 4. Soru türleri ve puanlama

| `question_type` | `scoring.method` | Zorunlu / yasak alanlar |
|---|---|---|
| `multiple_choice` | `multiple_choice_match` | `choices` ve `answer` zorunlu; `accepted_answers`, `code_spec`, `constraints` yasak |
| `short_answer` | `exact_match` | `answer` zorunlu, `accepted_answers` isteğe bağlı; `choices`, `code_spec`, `constraints` yasak |
| `numeric` | `numeric_match` | `answer` zorunlu; `scoring.tolerance` zorunlu; `choices`, `accepted_answers`, `code_spec`, `constraints` yasak |
| `code` | `unit_tests` | `code_spec` zorunlu; `choices`, `answer`, `accepted_answers`, `constraints` yasak |
| `constraint_check` | `constraint_check` | `constraints` zorunlu; `choices`, `answer`, `accepted_answers`, `code_spec` yasak |
| `open_ended` | `rubric` | `scoring.rubric_id` zorunlu; cevap anahtarı alanlarının hiçbiri bulunamaz |

**`scoring` alanındaki koşullu alanlar.**

- `normalization` her zaman zorunludur. İzinli değerler türe bağlıdır: `multiple_choice` için `choice_label`; `short_answer` için `tr_text` veya `tr_text_case_sensitive`; `numeric` için `numeric`; `code`, `constraint_check` ve `open_ended` için `none`.
- `tolerance` yalnızca ve her zaman `numeric_match` ile birlikte bulunur (mutlak tolerans, ≥ 0). Tam eşitlik isteniyorsa `0` yazılır.
- `rubric_id` yalnızca ve her zaman `rubric` ile birlikte bulunur ve `categories.json` içindeki bir rubriği göstermelidir.

**Çoktan seçmeli.** Seçenekler `choices` alanında tutulur ve etiketleri sırayla `A`, `B`, `C`… olmalıdır (2–5 seçenek); bu sıra etiketlerin benzersiz olmasını sağlar. `answer`, mevcut etiketlerden biri olmalıdır (4 seçenekli soruda `E` olamaz). Çeldiriciler makul ama kesin yanlış olmalı; doğru seçeneğin konumu kategori içinde dengeli dağıtılmalıdır.

**Kısa cevap.** `exact_match` bilinçli olarak katıdır. Türkçe ek alır ("Selanik'te", "Selanik'tir"); bu yüzden prompt cevap biçimini mutlaka belirtir: *"Yalnızca şehir adını yaz."* `accepted_answers` yazarın açık tercihidir: `answer` ve her `accepted_answers` girdisi ayrı ayrı normalize edilir, normalizasyon sonrası tekrar eden girdi hatadır. Hiçbir eşdeğerlik otomatik varsayılmaz: formül ile ad (örn. "CO2" ile "karbondioksit") eşdeğer sayılacaksa yazar bunu açıkça listeler ve insan inceleyici kararı onaylar. `CO₂` gibi uyumluluk karakterleri `CO2` ile eşleşmez (NFKC kullanılmaz).

**Sayısal.** Prompt "Yalnızca sayıyı yaz" demelidir. Cevap anahtarı noktalı ondalık ve binlik ayırıcısız yazılır (`1234.5`; `1.234,5` değil). Model cevabında `1.234` gibi birden fazla yoruma açık sayılar tahmin edilmez; belirsiz işaretlenir ve puanı 0 olur (ayrıntı: Bölüm 9).

## 5. Kategori notları

- **Türkçe Dil Anlama:** Yaygın ve tartışmasız deyim/atasözü anlamları seçilir; bölgesel veya tartışmalı kullanımlardan kaçınılır.
- **Mantıksal Akıl Yürütme:** Sonuç, verilen önermelerden kesin çıkmalıdır; "olabilir" türü cevaplar kullanılmaz.
- **Matematik:** Türkçe sözel problem; tek sonuç; para birimi ve birimler prompt'ta açık yazılır.
- **Genel Kültür ve Olgusal Doğruluk:** Zamanla değişmeyen olgular. Güncel durum ("şu anki başkan") sorulmaz. Gerçek veri setine alınan her maddede `references` zorunludur.
- **Türkçe Dilbilgisi:** Yazım ve noktalama TDK Yazım Kılavuzu gibi bir kaynağa göre doğrulanır. `references` içine kaynağın adı, varsa **sürümü** (`edition`) ve her zaman **erişim tarihi** (`accessed_date`) yazılır; hangi kuralın uygulandığı `verification.notes` içine eklenir. Büyük/küçük harfin anlam taşıdığı kısa cevaplarda `tr_text_case_sensitive` kullanılır.
- **Okuduğunu Anlama:** Metin özgün yazılır; cevap metinden doğrudan veya çok basit bir çıkarımla bulunur, dış bilgi gerektirmez.
- **Yaratıcı Yazarlık:** Bkz. Bölüm 10.

`references` kaydı (`name`, isteğe bağlı `url` ve `edition`, zorunlu `accessed_date`) şu kategorilerdeki gerçek veri seti maddelerinde zorunludur: `general_knowledge`, `turkish_grammar`, `factual_accuracy`. Fixture maddelerinde zorunlu değildir; bu yüzden FAC-900 gibi bir örnek, kaynak kaydı eklenmeden gerçek veri setine taşınamaz.

## 6. Talimat takibi kısıtları

Yalnızca program ile kesin doğrulanabilen kısıtlar kullanılır; "kısa yaz" veya "resmî bir dille yaz" gibi öznel talimatlar yasaktır. Kısıt değerleri her zaman string'dir (`"3"`). Satır sayısı ve sözcük sayısı değerleri ≥ 1 tam sayıdır; `forbidden_char` değeri tek karakterdir; `all_lowercase` / `all_uppercase` değeri `"true"` olur.

**Satır tanımı.** `\r\n` ve `\r`, `\n` kabul edilir; baştaki ve sondaki boşluk-yalnızı satırlar atılır; kalan metin `\n` ile bölünür; aradaki boş satırlar satır sayılır; satır içi boşluklar kırpılmaz.

| Tür | Davranış |
|---|---|
| `line_count` | Satır sayısı değere eşit |
| `line_prefix` | **Her** satır değerle başlar (yalnızca ilk satır değil); satır yoksa başarısız |
| `word_count_min` | Boşlukla ayrılmış sözcük sayısı ≥ değer |
| `word_count_max` | Boşlukla ayrılmış sözcük sayısı ≤ değer |
| `required_substring` | Ham metinde değer **alt dize** olarak geçer; büyük/küçük harf duyarlı |
| `forbidden_substring` | Ham metinde değer alt dize olarak geçmez; büyük/küçük harf duyarlı |
| `required_word` | Değer **tam sözcük** olarak geçer; Türkçe küçük harfe çevrilerek büyük/küçük harf duyarsız |
| `forbidden_word` | Değer tam sözcük olarak geçmez |
| `forbidden_char` | Değer (tek karakter) hiç geçmez |
| `starts_with` | Baştaki boşluklar atıldıktan sonra metin değerle başlar |
| `ends_with` | Sondaki boşluklar atıldıktan sonra metin değerle biter |
| `all_lowercase` | Metin == Türkçe küçük harfli hâli (büyük harf yok) |
| `all_uppercase` | Metin == Türkçe büyük harfli hâli (küçük harf yok) |

**Alt dize ile sözcük eşleşmesi karıştırılmaz.** Türkçe ek aldığı için "veri" kelimesi yasaklanırken iki ayrı niyet vardır: `forbidden_substring: "veri"` "verileri", "veritabanı" dahil harf dizisini içeren her metni ihlal sayar; `forbidden_word: "veri"` yalnızca tam sözcük olarak "veri" ("Veri", "veri,") geçerse ihlal sayar, "verileri" ihlal değildir. Sözcük sınırı harf/rakam olmayan karakterlerdir; apostrof sınırdır ("İstanbul'da" içinde "İstanbul" sözcüğü bulunur). Soru yazarı hangi davranışı istediğini seçer ve prompt'ta açıkça belirtir.

Puanlama iki biçimde raporlanır: **katı** (bir maddedeki tüm kısıtlar sağlandı = 1) ve **gevşek** (sağlanan kısıt oranı).

## 7. Kod soruları

- Python fonksiyonu istenir; `entry_point` fonksiyon adıdır. `args_json` konumsal argümanların JSON dizisi, `expected_json` beklenen dönüş değerinin JSON hâlidir; karşılaştırma tür duyarlıdır (`6` ile `6.0` farklıdır).
- **En az üç test** zorunludur, ancak testler görevin doğasına uygun seçilir. Her fonksiyona boş liste veya negatif değer testi eklenmez; yalnızca görev için anlamlıysa eklenir.
- **Güvenli yürütme zorunludur** (`sandbox_required: true`). Model kodu uygulamanın ana sürecinde asla çalıştırılmaz; her test ayrı, kaynak sınırlı bir alt süreçte (`timeout_seconds`, `memory_limit_mb`) çalışır. Kod önce statik denetimden geçer (izinli modüller dışında import yok). Bu önlemler en iyi çaba esaslıdır ve gerçek bir sandbox yerine geçmez; ayrıntı `categories.json` → `code_execution_policy` içindedir. Güvenli ortam yoksa kod maddeleri çalıştırılmaz ve `scoring_error` olarak raporlanır.
- İki ayrı metrik raporlanır: **test geçme oranı** (geçilen testler / tüm testler; kısmi başarı) ve **soru geçme oranı** (bir sorudaki bütün testlerin geçtiği soruların oranı). Kodlama kategori puanı soru geçme oranıdır.

## 8. Cevap anahtarı doğrulama ve insan incelemesi

**Programatik doğrulama ile insan incelemesi ayrı tutulur.** Programatik kontroller (şema doğrulaması, hesaplanan sonuç, referans çözümün testleri geçmesi) hatayı yakalar ama sorunun doğru, açık ve adil olduğunu kanıtlamaz. Bu kontroller `verification.notes` içine not olarak yazılabilir; hiçbiri `reviewed` değerini değiştirmez.

`reviewed: true` yalnızca şu koşulların **hepsi** sağlandığında kullanılır:

1. İnceleyici bir **insandır** (`reviewer_type: "human"`) ve sorunun **yazarından bağımsızdır** (`independent: true`).
2. İnceleyici hem **cevap anahtarını** hem **soru içeriğini** kontrol etmiştir (`checked.answer_key` ve `checked.question_content` ikisi de `true`).
3. `method` (`source_checked`, `worked_solution_checked` veya `expert_review`), `reviewer` (takma ad; kişisel veri yok) ve `reviewed_date` doldurulmuştur.

`reviewed: false` olan maddede bu alanların hiçbiri bulunamaz. Yapay zekâ yardımıyla yazılan sorular `source.authoring: "ai_assisted"` işaretlenir; yapay zekâ çıktısı tek başına inceleme sayılmaz. İncelenmemiş maddelerin oranı puan tablosunda gösterilir.

## 9. Türkçe normalizasyon ve cevap ayrıştırma

Normalizasyon yalnızca **karşılaştırma** içindir; ham prompt, ham cevap anahtarı ve modelin ham cevabı değiştirilmez. Profillerin adım adım tanımı ve örnekleri `categories.json` → `normalization_profiles` içindedir (testler o örnekleri koda karşı çalıştırır). Özet:

- `tr_text`: NFC (NFKC/NFKD yok), sıfır genişlikli karakterleri silme, tüm Unicode boşlukları tek boşluğa çevirme, tipografik apostrofları düz apostrofa çevirme, Türkçe küçük harf (`İ→i`, `I→ı`), uçlardaki tırnak ve cümle sonu noktalamasını silme.
- `tr_text_case_sensitive`: aynısı, ancak küçük harfe çevirme yok.
- `none`: metni birebir korur.
- **I/İ/ı/i ayrı harflerdir.** Python'un `lower()` işlevi `"İ"` için iki karakter, `"I"` için `i` üretir; bu yüzden Türkçe dönüşüm elle uygulanır. **Anlam taşıyan harfler birbirine çevrilmez:** ASCII'ye indirgeme (ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c) ve şapka silme (â→a) yapılmaz (`kâr ≠ kar`, `şu ≠ su`, `sık ≠ sik`).
- `choice_label`: yalnızca açıkça tanımlı biçimler kabul edilir: `B`, `B.`, `B)`, `(B)` ve `Cevap: B` (önek: cevap, yanıt, doğru cevap, doğru yanıt, doğru seçenek). Birden fazla farklı etiket varsa (`A veya B`) cevap **belirsiz** işaretlenir ve puanı 0 olur; cümle içinden harf ayıklanmaz.
- `numeric`: bir sayı ve isteğe bağlı tek birim sözcüğü kabul edilir. `1.234` / `1,234` gibi tek ayırıcı + tam 3 hane (solu 1–3 hane) belirsizdir; yorumlanmaz, `ambiguous_number` ile işaretlenir ve puanı 0 olur. `1.234,5`, `1,234.5` ve `1.234.567` açıktır. Birden fazla sayı içeren cevap `multiple_numbers` sayılır. Yalnızca ASCII rakamlar kabul edilir.

## 10. Yaratıcı yazarlık ve rubrikler

Açık uçlu cevaplar kelime eşleşmesiyle puanlanmaz. Pilot sürümde **yalnızca** `creative_writing_v1` rubriği kullanılır (0–4 ölçeği, 5 kriter). İleride başka açık uçlu görev türleri için ayrı rubrikler tanımlanabilir; her rubrik `categories.json` → `rubrics` içinde sürümüyle birlikte tanımlanır ve soru `scoring.rubric_id` ile onu gösterir. LLM hakem ve insan değerlendirmesi isteğe bağlıdır, ayrı raporlanır ve otomatik genel puana karıştırılmaz. v0.1.0'da bir madde için tek insan değerlendirmesi vardır; birden fazla değerlendirici desteği ileride eklenecektir.

## 11. İnceleme kontrol listesi

- [ ] Soru özgün veya izinli lisanslı kaynaktan; `license` ve `source.license` doğru kullanıldı.
- [ ] Tek bir doğru cevap var; kısa cevap ve sayısal sorularda cevap biçimi prompt'ta belirtilmiş.
- [ ] Çoktan seçmelide etiketler A, B, C… sırasında ve `answer` mevcut bir etiket.
- [ ] `scoring` alanları türe uygun: `normalization` var, `tolerance` yalnızca numeric'te, `rubric_id` yalnızca rubric'te.
- [ ] Olgusal/dilbilgisi maddelerinde `references` (kaynak adı, sürüm veya `accessed_date`) var.
- [ ] Kod sorusunda en az 3 anlamlı test ve `sandbox_required: true` var.
- [ ] Talimat kısıtlarında alt dize / sözcük ayrımı bilinçli yapıldı.
- [ ] `id` aralığı doğru (001–899 gerçek, 900–999 yalnızca fixture) ve `split` ile uyumlu.
- [ ] Programatik kontroller ile insan incelemesi ayrı kaydedildi; `reviewed: true` yalnızca bağımsız insan kontrolünden sonra.
- [ ] Şema ve tutarlılık doğrulamasından geçti; kişisel veri, telifli metin veya zararlı içerik yok.

## 12. Örnekler

Her kategoriden bir biçim örneği `sample_questions.jsonl` dosyasındadır (Space deposunda `tests/fixtures/` altında). Hepsi `-900` kimlikli, `split: "fixture"` ve `reviewed: false` işaretlidir; bu satırlar yalnızca şema ve doğrulayıcı testleri içindir ve `questions.jsonl` içine hiçbir zaman otomatik aktarılmaz.
