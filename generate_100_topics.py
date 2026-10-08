import json, random
from pathlib import Path

# Base templates for viral titles
TEMPLATES = {
    "Python": [
        ("Stop using len() like a junior", "if my_list: # truthy check\n  print('Not empty')", "Truthiness check"),
        ("This walrus operator saves 3 lines", "if (n := len(data)) > 10:\n  print(n)", "Walrus operator"),
        ("F-string trick that looks like magic", "name='Ali'\nprint(f'{name=}' ) # name='Ali'", "Debug f-string"),
        ("Unpacking trick senior devs use", "a, *middle, b = [1,2,3,4,5]", "Extended unpacking"),
        ("Dictionary merge in one line", "merged = {**dict1, **dict2}\n# or dict1 | dict2 in 3.9+", "Merge dicts"),
        ("Enumerate > range(len())", "for i, val in enumerate(arr):\n  print(i, val)", "Pythonic enumerate"),
        ("Zip two lists like a pro", "for name, age in zip(names, ages):\n  print(name, age)", "Zip"),
        ("Any() and All() will save you", "if all(x > 0 for x in nums):\n  print('All positive')", "Any All"),
        ("Lambda + map trick", "squared = list(map(lambda x: x**2, nums))", "Map lambda"),
        ("Context manager you ignore", "with open('file.txt') as f:\n  data = f.read()", "With statement"),
        ("Dataclass saves 20 lines", "from dataclasses import dataclass\n@dataclass\nclass User:\n  name: str\n  age: int", "Dataclass"),
        ("Try-except-else-finally flow", "try:\n  x=1/0\nexcept:\n  print('error')\nelse:\n  print('ok')", "Try else"),
        ("List comprehension filter", "[x for x in range(10) if x%2==0]", "Filter comprehension"),
        ("Set operations are underrated", "a = {1,2,3}\nb = {2,3,4}\na & b # {2,3}", "Set intersection"),
        ("Default dict trick", "from collections import defaultdict\nd = defaultdict(int)", "Default dict"),
    ],
    "JavaScript": [
        ("Destructuring that cleans your code", "const {name, age} = user;", "Object destructuring"),
        ("Spread operator magic", "const newArr = [...arr1, ...arr2];", "Spread"),
        ("Nullish coalescing saves crashes", "const val = input ?? 'default';", "Nullish coalescing"),
        ("Array map vs for loop", "const doubled = nums.map(n => n*2);", "Map"),
        ("Filter + map chaining", "users.filter(u=>u.active).map(u=>u.name)", "Chaining"),
        ("Async/await error handling", "try {\n  const data = await fetchData();\n} catch(e) {}", "Async try catch"),
        ("Object shorthand", "const user = {name, age}; // same as name:name", "Shorthand"),
        ("Template literals > concatenation", "console.log(`Hi ${name}, age ${age}`);", "Template literal"),
        ("Short-circuit evaluation", "isLoggedIn && showDashboard();", "Short circuit"),
        ("Array reduce in 10 sec", "const sum = nums.reduce((a,b)=>a+b, 0);", "Reduce"),
        ("Optional chaining is a lifesaver", "console.log(user?.address?.city);", "Optional chaining"),
        ("Debounce trick for search", "const debounce = (fn, d) => {let t; return (...a)=>{clearTimeout(t); t=setTimeout(()=>fn(...a), d)}}", "Debounce"),
        ("LocalStorage one-liner", "localStorage.setItem('user', JSON.stringify(user));", "LocalStorage"),
        ("Clone array without reference", "const clone = [...original];", "Clone"),
        ("Find vs filter", "const found = arr.find(x=>x.id===1);", "Find"),
    ],
    "TypeScript": [
        ("Interface vs Type - when to use", "interface User {name: string}\ntype ID = string | number", "Interface vs Type"),
        ("Utility types you must know", "Partial<User>, Required<User>, Pick<User,'name'>", "Utility types"),
        ("Generics explained simply", "function identity<T>(arg: T): T {return arg;}", "Generics"),
        ("Never type for exhaustive checks", "function assertNever(x: never): never {throw new Error();}", "Never"),
        ("as const for literal types", "const colors = ['red','blue'] as const;", "As const"),
        ("Optional properties", "type User = {name: string; age?: number}", "Optional"),
        ("Readonly prevents bugs", "type User = {readonly id: number}", "Readonly"),
        ("Union types power", "type Status = 'loading' | 'success' | 'error';", "Union"),
        ("Intersection types", "type Admin = User & {role: string}", "Intersection"),
        ("Keyof operator", "function getProp<T,K extends keyof T>(obj:T, key:K){return obj[key];}", "Keyof"),
    ],
    "Java": [
        ("Var keyword Java 10+", "var list = new ArrayList<String>();", "Var type inference"),
        ("Records save 50 lines", "record User(String name, int age) {}", "Records"),
        ("Switch expression Java 14+", "String result = switch(day) {\n  case MONDAY -> \"Work\";\n  default -> \"Rest\";\n};", "Switch expression"),
        ("Optional to avoid null", "Optional<User> user = findUser();\nuser.ifPresent(u->print(u));", "Optional"),
        ("Stream map filter", "list.stream().map(String::toUpperCase).toList();", "Stream map"),
        ("Try with resources", "try(var file = new FileReader(\"file.txt\")) {\n  // auto close\n}", "Try with resources"),
        ("List.of() immutable list", "var list = List.of(\"a\",\"b\",\"c\");", "List.of"),
        ("String formatted", "String s = \"Hi %s, age %d\".formatted(name, age);", "Formatted"),
        ("Sealed classes", "sealed class Shape permits Circle, Square {}", "Sealed"),
        ("Pattern matching instanceof", "if (obj instanceof String s) {\n  System.out.println(s.length());\n}", "Pattern matching"),
    ],
    "C++": [
        ("Range-based for loop", "for(auto& x : vec) {\n  cout << x;\n}", "Range for"),
        ("Smart pointers > raw pointers", "auto ptr = make_unique<int>(5);", "Smart pointers"),
        ("Move semantics", "vector<int> v2 = std::move(v1);", "Move"),
        ("Lambda in C++", "auto add = [](int a, int b){return a+b;};", "Lambda"),
        ("Constexpr", "constexpr int square(int x){return x*x;}", "Constexpr"),
        ("Structured bindings", "auto [key, value] = myMap[0];", "Structured bindings"),
        ("std::optional", "optional<int> maybe = 5;", "Optional"),
        ("Emplace_back vs push_back", "vec.emplace_back(1,2,3); // faster", "Emplace"),
        ("Using enum class", "enum class Color {Red, Blue};", "Enum class"),
        ("Auto return type", "auto func() {return 42;}", "Auto return"),
    ],
    "Go": [
        ("Go slices trick", "s := []int{1,2,3}\ns = append(s, 4)", "Append"),
        ("Maps in Go", "m := map[string]int{\"a\":1}\nm[\"b\"]=2", "Maps"),
        ("Goroutines", "go func() {\n  fmt.Println(\"concurrent\")\n}()", "Goroutine"),
        ("Channels", "ch := make(chan int)\nch <- 1\nval := <-ch", "Channels"),
        ("Defer", "defer fmt.Println(\"runs last\")", "Defer"),
        ("Pointers in Go", "func change(x *int) {\n  *x = 5\n}", "Pointers"),
        ("Interfaces", "type Writer interface {\n  Write([]byte) (int, error)\n}", "Interfaces"),
        ("Error handling", "if err != nil {\n  log.Fatal(err)\n}", "Error handling"),
        ("Structs", "type User struct {\n  Name string\n  Age int\n}", "Structs"),
        ("Select statement", "select {\ncase <-ch1:\ncase <-ch2:\n}", "Select"),
    ],
    "Rust": [
        ("Match is better than switch", "match x {\n  1 => println!(\"one\"),\n  _ => println!(\"other\")\n}", "Match"),
        ("Result type", "fn divide(a:i32,b:i32) -> Result<i32,String> {\n  if b==0 {Err(\"zero\".into())} else {Ok(a/b)}\n}", "Result"),
        ("Borrowing rules", "fn print(s: &String) {\n  println!(\"{}\", s);\n}", "Borrowing"),
        ("Iterators", "let sum: i32 = vec.iter().sum();", "Iterators"),
        ("Traits", "trait Animal {\n  fn make_sound(&self);\n}", "Traits"),
        ("Lifetime", "fn longest<'a>(x:&'a str, y:&'a str) -> &'a str", "Lifetime"),
        ("Unwrap_or", "let x = option.unwrap_or(0);", "Unwrap_or"),
        ("Vector macros", "let v = vec![1,2,3];", "Vec macro"),
        ("Enum with data", "enum Message {\n  Quit,\n  Move{x:i32, y:i32}\n}", "Enum data"),
        ("Closure", "let add = |a,b| a+b;", "Closure"),
    ],
    "SQL": [
        ("JOIN types explained", "SELECT * FROM users\nJOIN orders ON users.id=orders.user_id;", "JOIN"),
        ("GROUP BY + HAVING", "SELECT dept, COUNT(*) FROM emp\nGROUP BY dept HAVING COUNT(*)>5;", "Group by having"),
        ("Window functions", "SELECT name, AVG(salary) OVER(PARTITION BY dept) FROM emp;", "Window"),
        ("CTE", "WITH active_users AS (\n  SELECT * FROM users WHERE active=1\n)\nSELECT * FROM active_users;", "CTE"),
        ("CASE WHEN", "SELECT name,\n  CASE WHEN age<18 THEN 'minor' ELSE 'adult' END\nFROM users;", "Case when"),
        ("UNION vs UNION ALL", "SELECT * FROM table1\nUNION ALL\nSELECT * FROM table2;", "Union"),
        ("Indexing", "CREATE INDEX idx_name ON users(name);", "Index"),
        ("EXISTS", "SELECT * FROM users u\nWHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id=u.id);", "Exists"),
        ("COALESCE", "SELECT COALESCE(phone, email, 'no contact') FROM users;", "Coalesce"),
        ("LIMIT OFFSET", "SELECT * FROM users LIMIT 10 OFFSET 20;", "Pagination"),
    ],
    "Data Science": [
        ("Pandas head and info", "df.head()\ndf.info()\ndf.describe()", "Pandas basics"),
        ("Pandas iloc vs loc", "df.iloc[0:5] # by index\ndf.loc[df['age']>30] # by condition", "Iloc loc"),
        ("Matplotlib subplots", "fig, ax = plt.subplots(2,2)\nax[0,0].plot(x,y)", "Subplots"),
        ("Seaborn one-liner", "import seaborn as sns\nsns.heatmap(df.corr())", "Seaborn"),
        ("Train test split", "from sklearn.model_selection import train_test_split\nX_train, X_test = train_test_split(X, test_size=0.2)", "Train test split"),
        ("StandardScaler", "from sklearn.preprocessing import StandardScaler\nscaler = StandardScaler()\nX_scaled = scaler.fit_transform(X)", "Scaler"),
        ("Linear regression", "from sklearn.linear_model import LinearRegression\nmodel = LinearRegression()\nmodel.fit(X_train, y_train)", "Linear regression"),
        ("Confusion matrix", "from sklearn.metrics import confusion_matrix\ncm = confusion_matrix(y_true, y_pred)", "Confusion matrix"),
        ("Pandas apply", "df['new_col'] = df['col'].apply(lambda x: x*2)", "Apply"),
        ("Drop duplicates", "df.drop_duplicates()\ndf.drop_duplicates(subset=['email'])", "Drop duplicates"),
        ("Fill NA", "df.fillna(0)\ndf['col'].fillna(df['col'].mean())", "Fill NA"),
        ("Value counts", "df['category'].value_counts()\ndf['category'].value_counts(normalize=True)", "Value counts"),
        ("Correlation", "df.corr()\ndf['a'].corr(df['b'])", "Correlation"),
        ("Histogram", "plt.hist(df['age'], bins=20)\nplt.show()", "Histogram"),
        ("Boxplot", "plt.boxplot(df['salary'])\n# or sns.boxplot", "Boxplot"),
    ],
    "AI Ethics": [
        ("Bias in AI datasets", "# Check dataset balance\n# Ensure diverse representation", "Bias"),
        ("Explainable AI", "# Use SHAP, LIME to explain model\n# Black box is not ethical", "Explainable AI"),
        ("GDPR compliance", "# Right to be forgotten\n# Anonymize data", "GDPR"),
        ("Model cards", "# Document model: purpose, limitations, metrics\n# Like README for models", "Model cards"),
        ("Fairness metrics", "# Check equal opportunity\n# Demographic parity", "Fairness"),
        ("Data consent", "# Did users consent to training?\n# Opt-in not opt-out", "Consent"),
        ("Environmental cost of AI", "# Training GPT-3 = 500 tons CO2\n# Consider efficient models", "Environmental"),
        ("Deepfake ethics", "# Label AI generated content\n# Don't mislead", "Deepfake"),
        ("Open source licenses", "# MIT vs GPL vs Apache\n# Know what you can use", "Licenses"),
        ("Responsible AI checklist", "# 1. Bias check 2. Privacy 3. Explainability 4. Consent", "Checklist"),
    ]
}

topics = []
id_counter = 100

for lang, items in TEMPLATES.items():
    for title, code, expl in items:
        category = "tricks"
        if "basics" in expl.lower() or "basic" in title.lower():
            category = "basics"
        if lang == "Data Science":
            category = "data"
        if lang == "AI Ethics":
            category = "ethics"
        
        chart = None
        if lang == "Data Science" and random.random() > 0.5:
            chart = {"labels": ["A","B","C"], "values": [random.randint(20,90) for _ in range(3)]}
        
        topics.append({
            "id": f"{lang.lower()[:2]}{id_counter}",
            "language": lang,
            "title": title,
            "code": code,
            "explanation": expl,
            "category": category,
            "chart": chart
        })
        id_counter += 1

print(f"Generated {len(topics)} new topics")

# Load existing
import json
from pathlib import Path
existing_path = Path("topics.json")
existing = json.loads(existing_path.read_text())
print(f"Existing: {len(existing)}")

# Merge, avoid duplicates by title
existing_titles = set(t['title'] for t in existing)
new_unique = [t for t in topics if t['title'] not in existing_titles]

merged = existing + new_unique
existing_path.write_text(json.dumps(merged, indent=2))
print(f"Total now: {len(merged)} topics - {len(merged)/4:.1f} days at 4 vids/day = {len(merged)/120:.1f} months")
