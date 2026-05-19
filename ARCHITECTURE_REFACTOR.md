# Engineering Studio — Architecture Refactoring Specification

## Executive Summary

**Current State (BROKEN):**
- Frontend detects domains with hardcoded regex patterns
- Frontend hardcodes solving methods
- Backend does parameter extraction only
- Logic is duplicated across layers
- No structured method selection protocol

**Target State (CORRECT):**
- Backend: ALL domain classification, method generation, solver orchestration
- Frontend: ONLY input rendering, method selection UI, result display
- Single source of truth: backend
- Structured API contracts with schema validation

---

## Phase 1: Backend Refactoring

### 1.1 New Endpoint: `/api/analyze/problem`

**Purpose:** Frontend sends raw problem → Backend returns fully analyzed problem structure

**Request:**
```json
{
  "input": "Simply supported beam, L = 6m, UDL w = 10 kN/m",
  "type": "text"
}
```

**Response:**
```json
{
  "status": "ok",
  "problem_id": "p_12345",
  "domain": "structural",
  "problem_type": "simply_supported_beam",
  "confidence": 0.95,
  "input_summary": "Simply supported beam with UDL: span 6m, load 10kN/m",
  "parameters": {
    "L": 6.0,
    "w": 10000.0
  },
  "missing_parameters": [
    {
      "key": "E",
      "label": "Young's Modulus (E)",
      "unit": "Pa",
      "hint": "Typically 200 GPa for steel"
    }
  ],
  "available_methods": [
    {
      "id": "equilibrium",
      "name": "Equilibrium Method (ΣF=0, ΣM=0)",
      "description": "Apply equilibrium equations to find support reactions",
      "is_recommended": true,
      "prerequisites": [],
      "complexity": "basic"
    },
    {
      "id": "macaulay",
      "name": "Macaulay's Method",
      "description": "Use singularity functions for distributed loads",
      "is_recommended": false,
      "prerequisites": [],
      "complexity": "advanced"
    },
    {
      "id": "energy",
      "name": "Energy Method (Virtual Work)",
      "description": "Apply work-energy principle",
      "is_recommended": false,
      "prerequisites": ["deflection"],
      "complexity": "advanced"
    }
  ]
}
```

### 1.2 New Endpoint: `/api/compute/solve` (MODIFIED)

**New Request Schema:**

```json
{
  "problem_id": "p_12345",
  "method_id": "equilibrium",
  "parameters": {
    "L": 6.0,
    "w": 10000.0,
    "E": 200e9
  },
  "supplemental_params": {}
}
```

**Removed:** Domain detection, method selection logic — now backend-only

### 1.3 Backend Architecture: New Module `backend/method_generator.py`

**Responsibility:**
- Receives classified problem + extracted parameters
- Generates ALL valid solving methods
- Returns method metadata with prerequisites

**Key Functions:**
```python
def generate_methods_for_domain(
    domain: str,
    problem_type: str,
    parameters: dict,
    confidence: float
) -> list[MethodDefinition]:
    """Return all valid solving methods for this problem."""
    pass

@dataclass
class MethodDefinition:
    id: str                      # equilibrium, macaulay, energy
    name: str                    # Human-friendly name
    description: str             # One-liner explaining what it does
    is_recommended: bool         # Should be selected by default?
    prerequisites: list[str]     # Required sub-problems before this
    complexity: str              # basic, intermediate, advanced
    estimated_steps: int         # How many derivation steps
    solver_name: str             # Maps to backend solver function
    validation_checks: list[str] # What to verify in result
```

### 1.4 Backend: Method Metadata Registry

**New File:** `backend/methods_registry.py`

```python
METHODS_REGISTRY = {
    "structural": {
        "simply_supported_beam": {
            "equilibrium": MethodDefinition(
                id="equilibrium",
                name="Equilibrium Method (ΣF=0, ΣM=0)",
                description="Apply equilibrium equations to find support reactions",
                is_recommended=True,
                prerequisites=[],
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_beam_equilibrium",
                validation_checks=["reaction_sum", "moment_balance"]
            ),
            "macaulay": MethodDefinition(...),
            "energy": MethodDefinition(...),
        }
    },
    "algebra": {
        "simultaneous_equations": {
            "elimination": MethodDefinition(...),
            "substitution": MethodDefinition(...),
            "matrix": MethodDefinition(...),
            "cramers_rule": MethodDefinition(...),
        }
    },
    # ... all other domains
}
```

### 1.5 Backend: Problem Analysis Pipeline

**New Function in `main.py`:**

```python
@app.post("/api/analyze/problem")
async def analyze_problem(request: Request):
    """
    Tier 1 Response: Return problem structure + available methods.
    
    No solving happens here — just analysis and method generation.
    """
    raw_data = await request.json()
    user_input = raw_data.get("input", "").strip()
    
    # Layer 1: Fast classify
    l1_result = fast_classify(user_input)
    
    # Layer 2: Gemini extraction (if needed)
    routing = await route_and_extract(user_input, False, [], l1_result)
    routing = validate_and_normalize(routing, raw_query=user_input)
    
    sub_problems = routing.get("sub_problems", [])
    if not sub_problems:
        return JSONResponse({
            "status": "error",
            "message": "Could not classify problem"
        }, status_code=400)
    
    problem = sub_problems[0]
    domain = problem.get("domain", "unknown")
    problem_type = problem.get("problem_type", "general")
    
    missing = find_missing_params(
        domain, problem_type, 
        problem.get("parameters", {}), 
        user_input
    )
    
    # Generate all valid methods
    methods = generate_methods_for_domain(
        domain, problem_type, 
        problem.get("parameters", {}),
        problem.get("confidence", 0.8)
    )
    
    return JSONResponse({
        "status": "ok",
        "problem_id": f"p_{int(time.time() * 1000)}",
        "domain": domain,
        "problem_type": problem_type,
        "confidence": problem.get("confidence", 0.8),
        "input_summary": problem.get("input_summary", ""),
        "parameters": problem.get("parameters", {}),
        "missing_parameters": missing,
        "available_methods": [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "is_recommended": m.is_recommended,
                "prerequisites": m.prerequisites,
                "complexity": m.complexity
            }
            for m in methods
        ]
    })
```

### 1.6 Backend: Modified Solve Endpoint

```python
@app.post("/api/compute/solve")
async def solve(request: Request):
    """
    Tier 2 Response: Execute solving with selected method.
    
    Expects problem to be pre-analyzed.
    """
    raw_data = await request.json()
    problem_id = raw_data.get("problem_id")
    method_id = raw_data.get("method_id")
    parameters = raw_data.get("parameters", {})
    
    # Validate method_id matches domain
    # Validate parameters are complete
    # Execute solver with method_id
    # Stream results
```

---

## Phase 2: Frontend Refactoring

### 2.1 Remove ALL Logic Files

**DELETE:**
- `frontend/src/lib/methodDetector.js` — NO LONGER NEEDED
- All domain detection logic from components

### 2.2 New Hook: `useProblemAnalyzer.js`

```javascript
// frontend/src/lib/useProblemAnalyzer.js
export function useProblemAnalyzer() {
  const [analysis, setAnalysis] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  const analyze = async (input) => {
    setIsAnalyzing(true);
    try {
      const response = await fetch(
        `${import.meta.env.VITE_BACKEND_URL}/api/analyze/problem`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input, type: 'text' })
        }
      );
      
      if (!response.ok) throw new Error('Analysis failed');
      const data = await response.json();
      setAnalysis(data);
      return data;
    } catch (err) {
      setAnalysis(null);
      throw err;
    } finally {
      setIsAnalyzing(false);
    }
  };
  
  return { analysis, isAnalyzing, analyze };
}
```

### 2.3 New Component: `MethodSelector.jsx`

```javascript
// frontend/src/components/MethodSelector.jsx
export default function MethodSelector({ methods, onSelect, isLoading }) {
  if (!methods?.length) return null;
  
  return (
    <div className="method-selector">
      {methods.map(method => (
        <button
          key={method.id}
          onClick={() => onSelect(method.id)}
          disabled={isLoading}
          className={method.is_recommended ? 'recommended' : ''}
        >
          <div className="method-name">{method.name}</div>
          <div className="method-description">{method.description}</div>
          <div className="method-complexity">{method.complexity}</div>
        </button>
      ))}
    </div>
  );
}
```

### 2.4 Modified App.jsx Flow

**OLD (WRONG):**
```
User input 
→ Frontend detectDomain() [WRONG]
→ Frontend getMethodsForDomain() [WRONG]
→ Show method popup [WRONG]
→ Send to backend
```

**NEW (CORRECT):**
```
User input
→ Send to /api/analyze/problem [BACKEND]
→ Backend returns: {domain, methods[], missing_params}
→ IF missing_params: show parameter dialog
→ IF multiple methods: show method selector
→ User selects method
→ Send to /api/compute/solve with method_id
→ Stream derivation
```

### 2.5 New App.jsx Structure

```javascript
export default function App() {
  const [entries, setEntries] = useState([]);
  const { analysis, isAnalyzing, analyze } = useProblemAnalyzer();
  const [methodChoice, setMethodChoice] = useState(null);
  
  const handleCompute = async () => {
    const query = inputText.trim();
    
    // STEP 1: Analyze problem (backend only)
    try {
      const analysis = await analyze(query);
      
      // STEP 2: Check if missing parameters
      if (analysis.missing_parameters?.length > 0) {
        // Show parameter dialog
        // User fills in → retry analyze
        return;
      }
      
      // STEP 3: Check if multiple methods
      if (analysis.available_methods?.length > 1) {
        // Show method selector
        // User selects → proceed
        setMethodChoice(analysis.available_methods[0]); // or wait for selection
        return;
      }
      
      // STEP 4: Auto-select single method
      const method = analysis.available_methods[0];
      
      // STEP 5: Execute solve
      await executeSolve(
        analysis.problem_id,
        method.id,
        analysis.parameters
      );
      
    } catch (err) {
      // Show error
    }
  };
  
  const executeSolve = async (problemId, methodId, parameters) => {
    const endpoint = `${import.meta.env.VITE_BACKEND_URL}/api/compute/solve`;
    const response = await fetch(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        problem_id: problemId,
        method_id: methodId,
        parameters
      })
    });
    
    // Stream and render...
  };
  
  return (
    <div>
      {/* ... */}
      {isAnalyzing && <div>Analyzing problem...</div>}
      {analysis?.missing_parameters && <ParameterDialog />}
      {analysis?.available_methods && <MethodSelector />}
      {/* ... */}
    </div>
  );
}
```

---

## Phase 3: API Contract Specification

### Request/Response Types

```python
# backend/schemas.py

from pydantic import BaseModel
from typing import Optional, List

class MethodDefinition(BaseModel):
    id: str
    name: str
    description: str
    is_recommended: bool
    prerequisites: List[str]
    complexity: str  # basic, intermediate, advanced
    estimated_steps: int

class MissingParameter(BaseModel):
    key: str
    label: str
    unit: Optional[str]
    hint: Optional[str]
    example_value: Optional[float]

class ProblemAnalysisRequest(BaseModel):
    input: str
    type: str = "text"  # text, image

class ProblemAnalysisResponse(BaseModel):
    status: str
    problem_id: str
    domain: str
    problem_type: str
    confidence: float
    input_summary: str
    parameters: dict
    missing_parameters: List[MissingParameter]
    available_methods: List[MethodDefinition]

class SolveRequest(BaseModel):
    problem_id: str
    method_id: str
    parameters: dict
    supplemental_params: Optional[dict]

class DerivationStep(BaseModel):
    type: str  # step, equation, diagram, verification
    content: str
    latex: Optional[str]
    metadata: Optional[dict]

class SolveResponse(BaseModel):
    type: str  # final
    answer: str
    derivation_steps: List[DerivationStep]
    verification: Optional[dict]
```

---

## Phase 4: Error Handling Architecture

### Structured Error Protocol

Every backend response includes error context:

```json
{
  "status": "error",
  "stage": "parser | router | method_gen | solver | render",
  "code": "ERR_CODE",
  "message": "Human-friendly message",
  "recoverable": true,
  "suggestion": "What the user should do"
}
```

**Stages:**
- `parser`: Input could not be parsed
- `router`: Domain classification failed
- `method_gen`: No solving methods available
- `solver`: Computation error
- `render`: Result formatting failed

---

## Phase 5: Verification & Validation

### Backend Verification System

Every solver output must include:

```python
@dataclass
class VerificationResult:
    passed: bool
    checks: List[VerificationCheck]
    
    # Example: beam equilibrium
    # ✓ Sum of vertical forces = 0
    # ✓ Sum of moments = 0
    # ✓ Reactions are positive (physically valid)
```

---

## Migration Checklist

- [ ] Create `backend/method_generator.py`
- [ ] Create `backend/methods_registry.py`
- [ ] Create `backend/schemas.py` with Pydantic models
- [ ] Add `/api/analyze/problem` endpoint
- [ ] Modify `/api/compute/solve` to use `problem_id` + `method_id`
- [ ] Remove `frontend/src/lib/methodDetector.js`
- [ ] Create `frontend/src/lib/useProblemAnalyzer.js`
- [ ] Create `frontend/src/components/MethodSelector.jsx`
- [ ] Refactor `App.jsx` with new analysis flow
- [ ] Add comprehensive error handling
- [ ] Add verification step before returning result
- [ ] Document new API contracts
- [ ] Add integration tests

---

## Benefits of This Architecture

✅ **Single Source of Truth:** Backend owns all engineering logic  
✅ **Scalable:** Adding new domains = 1 method registry entry  
✅ **Debuggable:** All logic in one place, no frontend guessing  
✅ **Testable:** Backend can be tested independently  
✅ **Auditable:** Engineering decisions logged on server  
✅ **Deterministic:** No frontend-backend sync issues  
✅ **Professional:** Like MATLAB/Mathematica, not AI chat  

