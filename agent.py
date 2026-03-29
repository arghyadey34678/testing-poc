"""
Unified POM Agent
=================
Combined Purchase Order Management agent supporting:
- API operations (CREATE/UPDATE/CHECK PO via REST APIS)
- Natural language processing with Gemini
- Deployment-independent configuration
"""

import os
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

#Core imports
import requests
From google import genai
from google.genai.types import (
Tool,
HttpOptions,
ToolCodeExecution,
GenerateContentConfig,
)
#Lazy imports: json is used frequently, but import it here for consistency
import json
try:
from google.adk.agents import BaseAgent
except ImportError:
#Fallback for environments without ADK
BaseAgent object
#PO Transmission Destination Codes Mapping (DEST_CD, destCd)
#Maps destination code values from EXTNL_ORD_TRNSM_STAT table
DESTINATION_CODE_MAP = {
'1': 'Finance',
'2': 'EDW',
'3': 'Containerization',
' 5': 'Purchase_Order_Repository',
'6': 'DCPPO',
'9': 'PREPACKREPORT',
'7': 'SDC',
'19': 'EDI_Domestic',
'21': 'DFC',
'22': 'Transportation',
'27': 'EDI_Import',
'29': 'DCM_Order',
'30': 'CIM_CarrierInvoiceManagement',
'34': 'RDC',
'35': 'AGGROSTCREATE',
'36': 'GCPPUBSUB',
'37': 'Transfers',
'39': 'EDI Domestic
}

class POMAgent(BaseAgent):
    """Unified Purchase Order Management Agent.
    
    Combines:
    - API-based operations (CREATE/UPDATE/CHECK PO)
    - Natural language understanding
    - OAuth2 authentication
    - Template-based payload generation
    """
    def __init__(self, project_id: Optional[str] = None, location: str = "us-central1", enable_code_execution: bool = True, **kwargs):
        """Initialize the unified POM Agent.

        Args:
            project_id: Google Cloud project ID (optional, defaults to np-sc-inventory-execution)
            location: Google Cloud location (default: us-central1 - must match Agent Engine deployment)
            enable_code_execution: Enable Gemini code execution (default: True)
        """
        try:
            # Initialize BaseAgent if it's not just object
            if BaseAgent != object:
                # Provide required 'name' field for BaseAgent
                if 'name' not in kwargs:
                    kwargs['name'] = 'pom_testing_agent'
                super().__init__(**kwargs)
            
            # Use __dict__ to set attributes directly (bypass Pydantic validation)
            if project_id is None:
                # Default to np-sc-inventory-execution for cloud deployments
                project_id = os.getenv('GOOGLE_CLOUD_PROJECT', 'np-sc-inventory-execution')
            print(f"[POMAgent] Initializing with project id: {project_id}")
            self.__dict__['project_id'] = project_id
            self.__dict__['location'] = location

            # Set up environment variables for Vertex AI
            os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
            os.environ["GOOGLE_CLOUD_LOCATION"] = location
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

            # Initialize Gemini client
            self.__dict__['client'] = genai.Client(http_options=HttpOptions(api_version="v1"))
            self.__dict__['model_id'] = "gemini-2.5-pro"

            # Initialize Vertex AI once during startup
            try:
                from google.cloud import aiplatform
                aiplatform.init(project=project_id, location="us-east1")
                print(f"[POMAgent] Vertex AI initialized for project: {project_id}")
            except Exception as e:
                print(f"[POMAgent] Warning: Vertex AI initialization failed: {e}")
            
             # RAG Corpus configuration
            self.__dict__['rag_corpus_name'] = "projects/np-sc-inventory-execution/locations/us-east1/ragCorpora/7991637538768945152"
            self.__dict__['use_rag_corpus'] = True # Enable RAG corpus
            self.__dict__['rag_model'] = None # Cache for RAG model instance
            self.__dict__['rag_corpus_obj'] = None # Cache for RagCorpus object

            # Connection pooling and token caching for performance
            self.__dict__['http_session'] = requests.Session() # Reuse connections
            self.__dict__['token_cache'] = {} # Cache tokens: {api_name: {'token': str, 'expires_at': float}}
            print(f"[POMAgent] RAG Corpus configured: {self.rag_corpus_name}")

            # Enable code execution tool if requested
            #Enable code execution tool if requested
            self.__dict__['enable_code_execution'] = enable_code_execution
            if enable_code_execution:
                self.__dict__['code_execution_tool'] = Tool(code_execution=ToolCodeExecution())

            #Set up paths relative to this module
        	self.__dict__['base_dir'] = Path(__file__).parent
        	self.__dict__['config_path'] = self.base_dir / "resources" / "configs" / "pom_configs.md"
        	self.__dict__['template_path'] = self.base_dir / "resources" / "templates"
        	self.__dict__['sample_input_output_path'] = self.base_dir / "resources" / "samples"
        	self.__dict__['sample_code_path'] = self.base_dir / "resources" / "code_samples"
        	self.__dict__['prompt_path'] = self.base_dir / "resources" / "prompts"
        	self.__dict__['rag_path'] = self.base_dir / "resources" / "rag"
        
        	#Load resources with error handling
        	print(f"[POMAgent] Loading resources from: {self.base_dir}")
            self.__dict__['api_config'] = self._load_api_config()
            self.__dict__['templates'] = self._load_templates()
            self.__dict__['samples'] = self._load_samples()
            self.__dict__['sample_code'] = self._load_sample_code()
            self.__dict__['rag_knowledge'] = self._load_rag_knowledge()
            print(f"[POMAgent] Initialization complete. Project: {project_id}")
        except Exception as e:
            print(f"[POMAgent] Warning: Initialization error: {str(e)}")
            #Set minimal defaults to allow agent to function
            self.__dict__['project_id'] = project_id or "np-sc-inventory-execution"
            self.__dict__["location"] = location
            self.__dict__['client'] = genai.Client(http_options=HttpOptions(api_version="v1"))
            self.__dict__['model_id'] = "gemini-2.5-pro"
            self.__dict__['api_config'] = {}
            self.__dict__['templates'] = {}
            self.__dict__['samples'] = {}
            self.__dict__['sample_code'] = {}
            self.__dict__['rag_knowledge'] = {}
            print(f"[POMAgent] Fallback initialization complete")

    def _load_api_config(self) -> Dict[str, Any]:
        """Load API configuration from pom_configs.md (markdown format)"""
        config = {}

            try:
                with open(self.config_path, 'r') as f:  
                    content = f.read()
                #Parse markdown format: ### api_name followed by - **field**: value
                import re
                #Find all API sections (### api_name)
                api_sections = re.split(r'###\s+(\w+)', content)[1:] # Skip first empty section
                #Process pairs of (api_name, api_content)
                for i in range(0, len(api_sections), 2):
                    if i+1 >= len(api_sections):
                        break
                    api_name = api_sections[i].strip()
                    api_content = api_sections[i+1]
                    #Parse each field from markdown bullets
                    api_config = {}
                    for line in api_content.split('\n'):
                        match = re.match(r'-\s+\*\*(\w+)\*\*:\s*(.+)', line)
                        if match:
                            field_name = match.group(1)
                            field_value = match.group(2).strip()
                            #Convert boolean strings
                            if field_value.lower() == 'true':
                                field_value = True
                            elif field_value.lower() == 'false':
                                field_value = False
                                
                            api_config['field_name'] = field_value
                if api_config: # only add if we found configuration
                    config['api_name'] = api_config
            print(r"[POMAgent] Loaded (len(config)) API configurations: {list(config.keys())}")

            except Exception as e:
                print(f"[Warning: Error loading config: {e}")
                import traceback
                traceback.print_exc()
            return config

    def _load_templates(self) -> Dict[str, Any]: # Load JSON templates
        templates = {}
        try:
            # Create PO templates
            input_template = self.template_path / "create_po_api_input_template.json"
            if input_template.exists():
                with open(input_template, 'r') as f:
                    templates['create_po_input'] = json.load(f)
            
            output_template = self.template_path / "create_po_api_output_template.json"
            if output_template.exists():
                with open(output_template, 'r') as f:
                    templates['create_po_output'] = json.load(f)

            # Update PO templates
            update_input_template = self.template_path / "update_po_api_input_template.json"
            if update_input_template.exists():
                with open(update_input_template, 'r') as f:
                    templates['update_po_input'] = json.load(f)

            update_output_template = self.template_path / "update_po_api_output_template.json"
            if update_output_template.exists():
                with open(update_output_template, 'r') as f:
                    templates['update_po_output'] = json.load(f)       
        except Exception as e:
            print(f"[Warning: Error loading templates: {e}")
        return templates

    def _load_samples(self) -> Dict[str, Any]:
        # Load JSON samples from 'sample_input_output' folder (excluding PO type-specific samples)
        samples = {}
        try:
            # Output sample
            output_sample = self.sample_input_output_path / "create_po_api_output_sample.json"
            if output_sample.exists():
                with open(output_sample, 'r') as f:
                    samples['create_po_output'] = json.load(f)

            # Update PO samples
            update_input_sample = self.sample_input_output_path / "update_po_api_input_sample.json"
            if update_input_sample.exists():
                with open(update_input_sample, 'r') as f:
                    samples['update_po_input'] = json.load(f)

            update_output_sample = self.sample_input_output_path / "update_po_api_output_sample.json"
            if update_output_sample.exists():
                with open(update_output_sample, 'r') as f:
                    samples['update_po_output'] = json.load(f)

            # Token sample
            token_sample = self.sample_input_output_path / "token_output_sample.json"
            if token_sample.exists():
                with open(token_sample, 'r') as f:
                    samples['token_output'] = json.load(f)
            
            # Note: PO type-specific samples are loaded on-demand via _load_po_type_sample()

        except Exception as e:
            print(f"[Warning: Error loading samples: {e}")
        return samples

    def _load_po_type_sample(self, po_type: str) -> Optional[Dict[str, Any]]:
        """Load PO type-specific sample on demand from po_create_samples subdirectory.

        Args:
            po_type: PO type like 'BDC_DOMESTIC', 'DFC_IMPORT', etc.

        Returns:
            Sample data dictionary or None if not found
        """
        try:
            po_create_samples_dir = self.sample_input_output_path / "po_create_samples"
            po_type_file = po_create_samples_dir / f"{po_type}_create_po_api_input_sample.json"

            if po_type_file.exists():
                with open(po_type_file, 'r') as f:
                    sample_data = json.load(f)
                print(f"[POMAgent] Loaded {po_type} sample from {po_type_file}")
                return sample_data
            else:
                print(f"[POMAgent] Sample file not found: {po_type_file}")
                return None
        except Exception as e:
            print(f"[POMAgent] Error loading {po_type} sample: {e}")
            return None
        
    def _load_sample_code(self) -> Dict[str, str]:
            """Load sample code from Sample_code folder"""
            sample_code = {}
            try:
                # Create PO sample code
                create_code = self.sample_code_path / "sample_po_create_code.md"
                if create_code.exists():
                    with open(create_code, 'r') as f:
                        sample_code['create_po_code'] = f.read()

                # Update PO sample code
                update_code = self.sample_code_path / "sample_po_update_code.md"
                if update_code.exists():
                    with open(update_code, 'r') as f:
                        sample_code['update_po_code'] = f.read()

                # Token sample code
                token_code = self.sample_code_path / "samle_token_create_code.md"
                if token_code.exists():
                    with open(token_code, 'r') as f:
                        sample_code['token_code'] = f.read()
            except Exception as e:
                print(f"Warning: Error loading sample code: {e}")
            return sample_code

    def _get_access_token(self, api_name: str) -> Optional[str]:
        """Get OAuth2 access token for API authentication with caching for performance"""
        if api_name not in self.api_config:
            print(f"[_get_access_token] ERROR: API '{api_name}' not found in config")
            return None

        config = self.api_config[api_name]
        if not config.get('is_secured'):
            print(f"[_get_access_token] API '{api_name}' is not secured, skipping token")
            return None

        # Check cache first (expires after 50 minutes - tokens typically last 60 mins)
        import time
        current_time = time.time()
        if api_name in self.token_cache:
            cached = self.token_cache[api_name]
            if cached['expires_at'] > current_time:
                print(f"[_get_access_token] ✓ Using cached token for '{api_name}'")
                return cached['token']

        try:
            token_url = config['token_api']
            print(f"[_get_access_token] Calling token API for '{api_name}': {token_url}")

            payload = {
                'grant_type': 'client_credentials',
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'scope': config['client_scope']
            }

            print(f"[_get_access_token] Requesting token with client_id: {config['client_id']}")
            print(f"[_get_access_token] POST Request: {token_url}")
            print(f"[_get_access_token] Request payload: grant_type={payload['grant_type']}, scope={payload['scope']}")

            # Use session for connection pooling
            response = self.http_session.post(token_url, data=payload, timeout=300)
            print(f"[_get_access_token] Token API response status: {response.status_code}")
            response.raise_for_status()
            token = response.json().get('access_token')

           if token:
                # Cache token with 50-minute expiration
                self.token_cache[api_name] = {
                    'token': token,
                    'expires_at': current_time + 3000 # 50 minutes
                }
                print(f"[_get_access_token] Successfully obtained and cached access token (length: {len(token)})")
                return token
            else:
                print(f"[_get_access_token] ERROR: Token API returned 200 but no access_token in response")
                return None
        except Exception as e:
            print(f"[_get_access_token] ERROR getting access token: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generate_po_request_id(self) -> int:
        """Generate a random integer value for poRequestId"""
        return random.randint(100000000, 999999999)

    def _load_rag_knowledge(self) -> str:
        """Load RAG knowledge base from local files"""
        try:
            knowledge = []
            rag_files = list(self.rag_path.glob("*.md"))
            for file_path in rag_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    knowledge.append(f.read())
            combined_knowledge = "\n\n".join(knowledge)
            print(f"[POMAgent] Loaded local RAG knowledge: {len(rag_files)} files, {len(combined_knowledge)} chars")
            return combined_knowledge
        except Exception as e:
            print(f"[POMAgent] Warning: Error loading RAG knowledge: {e}")
            return ""

    def handle_knowledge_query(self, user_query: str) -> Dict[str, Any]:
        """Handle knowledge base queries about POM codes, statuses, etc."""
        try:
            # Query the RAG corpus or local knowledge base
            knowledge = self._query_rag_corpus(user_query, similarity_top_k=3)

            if knowledge and len(knowledge.strip()) > 5:
                # Use the LLM to generate a concise answer from the knowledge
                answer = self._answer_from_knowledge(user_query, knowledge)
                return {
                    'success': True,
                    'answer': answer,
                    'message': answer,
                    'operation': 'KNOWLEDGE_QUERY'
                }
                
            else:
                return {
                    'success': False,
                    'message': 'I could not find information about that in the knowledge base.',
                    'operation': 'KNOWLEDGE_QUERY'
                }

        except Exception as e:
            print(f"[handle_knowledge_query] Error: {e}")
            return {
                'success': False,
                'error': f'Error querying knowledge base: {str(e)}',
                'operation': 'KNOWLEDGE_QUERY'
            }

    def _answer_from_knowledge(self, query: str, knowledge: str) -> str:
        """Use the language model to answer a query based on provided knowledge."""
        try:
            prompt = f"""Answer the following question based *only* on the provided context.
If the answer is not in the context, say you don't know.

Context:
---
{knowledge}
---

Question: {query}
Answer:"""

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=GenerateContentConfig(temperature=0),
            )
            return response.text.strip()
        except Exception as e:
            print(f"[POMAgent] Error answering from knowledge: {e}")
            return "I encountered an error while trying to answer the question."

    def _answer_from_knowledge(self, query: str, knowledge: str) -> str:
        """Use the language model to answer a query based on provided knowledge."""
        try:
            prompt = f"""Answer the following question based *only* on the provided context.
If the answer is not in the context, say you don't know.

Context:
---
{knowledge}
---

Question: {query}
Answer:"""

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=GenerateContentConfig(temperature=0),
            )
            return response.text.strip()
        except Exception as e:
            print(f"[POMAgent] Error answering from knowledge: {e}")
            return "I encountered an error while trying to answer the question."

    def _query_rag_corpus(self, query: str, similarity_top_k: int = 2) -> str:
        """Query RAG corpus or local knowledge for relevant information"""
        try:
            # If RAG corpus is enabled, use Vertex AI RAG
            if self.use_rag_corpus and self.rag_corpus_name:
                try:
                    from vertexai.preview import rag
                    from vertexai.preview.generative_models import Tool

                    print(f"[POMAgent] Querying RAG corpus: {self.rag_corpus_name}")

                    # Query the RAG corpus
                    response = rag.retrieval_query(
                        rag_resources=[
                            rag.RagResource(
                                rag_corpus=self.rag_corpus_name,
                            )
                        ],
                        text=query,
                        similarity_top_k=similarity_top_k,
                    )

                    # Extract contexts from response
                    if response and hasattr(response, 'contexts') and response.contexts:
                        contexts = []
                        for ctx in response.contexts.contexts:
                            if hasattr(ctx, 'text'):
                                contexts.append(ctx.text)

                        if contexts:
                            combined = "\n\n".join(contexts)
                            print(f"[POMAgent] ✓ Retrieved {len(contexts)} contexts from RAG corpus ({len(combined)} chars)")
                            return combined

                    print(f"[POMAgent] No results from RAG corpus, falling back to local knowledge")

                except Exception as rag_error:
                    print(f"[POMAgent] RAG corpus error: {rag_error}, falling back to local knowledge")

            # Fallback: search local knowledge with better section extraction
            if self.rag_knowledge:
                print(f"[POMAgent] Searching local knowledge for: {query[:100]}...")
                # Extract code numbers/identifiers from query
                import re
                code_numbers = re.findall(r'\b\d+\b|\b[A-Z]{2,}\b', query)
                print(f"[POMAgent] Extracted code numbers: {code_numbers}")

                # Find relevant sections
                lines = self.rag_knowledge.split('\n')
                relevant_sections = []
                current_section = []
                in_relevant_section = False

                # Check what keywords are in the query
                query_keywords = ['status', 'transaction', 'type', 'reason', 'code', 'destination', 'cancel', 'order']
                query_lower = query.lower()
                query_has_keywords = [kw for kw in query_keywords if kw in query_lower]
                print(f"[POMAgent] Query keywords found: {query_has_keywords}")

                for line in lines:
                    # Section header detection (## headings)
                    if line.startswith('##'):
                        # Save previous section if relevant
                        if in_relevant_section and current_section:
                            relevant_sections.extend(current_section)
                            relevant_sections.append('')
                        current_section = [line]
                        # Check if this section header is relevant to query keywords
                        in_relevant_section = any(keyword in line.lower() for keyword in query_has_keywords)
                    else:
                        current_section.append(line)
                        # Check if line matches any code numbers
                        if code_numbers and any(f'**{num}**' in line or f'- **{num}**' in line for num in code_numbers):
                            in_relevant_section = True

                # Add last section if relevant
                if in_relevant_section and current_section:
                    relevant_sections.extend(current_section)

                if relevant_sections:
                    result = '\n'.join(relevant_sections[:150])
                    print(f"[POMAgent] ✓ Found {len(relevant_sections)} relevant lines in local knowledge")
                    return result

                print(f"[POMAgent] No sections matched, trying simple keyword search...")
                # Fallback: simple keyword matching
                relevant_lines = [line for line in lines if any(word in line.lower() for word in query_lower.split()[:5])]
                if relevant_lines:
                    result = '\n'.join(relevant_lines[:100])
                    print(f"[POMAgent] ✓ Found {len(relevant_lines)} lines via keyword matching")
                    return result

                print(f"[POMAgent] No matches found in local knowledge")
                return ""

        except Exception as e:
            print(f"[POMAgent] Error querying RAG: {e}")
            return ""
    
    def _check_po_type_completeness(self, user_instruction: str) -> Dict[str, Any]:
        """Check if user provided complete PO type information (location type + domestic/import)"""
        check_prompt = f"""Analyze the following user instruction and determine if the user specified:
        1. Location type (BDC, RDC, RDCX, IFC, DFC, TLD, or SDC)
        2. Order classification (Domestic or Import)

        User Instruction: {user_instruction}

        Return a JSON response with ONLY these fields:
        {{
            "has_location_type": true/false,
            "location_type": "BDC/RDC/RDCX/IFC/DFC/TLD/SDC or null",
            "has_classification": true/false,
            "classification": "DOMESTIC/IMPORT or null"
        }}

        Examples:
        - "Create BDC Domestic PO" -> {{"has_location_type": true, "location_type": "BDC", "has_classification": true, "classification": "DOMESTIC"}}
        - "Create BDC PO" -> {{"has_location_type": true, "location_type": "BDC", "has_classification": false, "classification": null}}
        - "Create a purchase order" -> {{"has_location_type": false, "location_type": null, "has_classification": false, "classification": null}}
        - "Create import PO" -> {{"has_location_type": false, "location_type": null, "has_classification": true, "classification": "IMPORT"}}

        Return ONLY valid JSON, no explanations.
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=check_prompt,
                config=GenerateContentConfig(temperature=0),
            )
            response_text = response.text.strip()

            # Extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                return result
            else:
                return {"has_location_type": False, "location_type": None, "has_classification": False, "classification": None}
        except Exception as e:
            print(f"[POMAgent] Error checking PO type completeness: {e}")
            return {"has_location_type": False, "location_type": None, "has_classification": False, "classification": None}

    
    def _detect_po_type(self, user_instruction: str) -> str:
        """Detect PO type from user instruction using NLP and intent recognition"""
        detect_prompt = f"""Analyze the following user instruction and identify the Purchase Order (PO) type.

        Available PO types:
        1. BDC Domestic - Bulk Distribution Center, domestic orders
        2. RDC Domestic - Regional Distribution Center, domestic orders
        3. RDCX Domestic - Regional Distribution Center Cross-dock, domestic orders
        4. IFC Domestic - Import Flow-through Center, domestic orders
        5. DFC Domestic - Direct Fulfillment Center, domestic orders
        6. DFC Import - Direct Fulfillment Center, import orders
        7. TLD Import - Third-party Logistics Distribution, import orders
        8. SDC Import - Supplier Direct Center, import orders

        Look for keywords like:
        - "BDC" + "domestic" -> BDC_DOMESTIC
        - "RDC" + "domestic" -> RDC_DOMESTIC
        - "RDCX" + "domestic" or "cross-dock" or "crossdock" -> RDCX_DOMESTIC
        - "IFC" + "domestic" -> IFC_DOMESTIC
        - "DFC" + "domestic" -> DFC_DOMESTIC
        - "DFC" + "import" -> DFC_IMPORT
        - "TLD" + "import" -> TLD_IMPORT
        - "Transload" + "import" -> TLD_IMPORT
        - "SDC" + "import" or "supplier direct" -> SDC_IMPORT

        User Instruction: {user_instruction}

        Return ONLY ONE of these exact values: BDC_DOMESTIC, RDC_DOMESTIC, RDCX_DOMESTIC, IFC_DOMESTIC, DFC_DOMESTIC, DFC_IMPORT, TLD_IMPORT, SDC_IMPORT
        If no specific type is mentioned, return: INCOMPLETE

        PO Type:"""

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=detect_prompt,
                config=GenerateContentConfig(temperature=0),
            )
            po_type = response.text.strip().upper()

            # Validate the detected PO type
            valid_types = ['BDC_DOMESTIC', 'RDC_DOMESTIC', 'RDCX_DOMESTIC', 'IFC_DOMESTIC', 'DFC_DOMESTIC', 'DFC_IMPORT', 'TLD_IMPORT', 'SDC_IMPORT']
            if po_type in valid_types:
                print(f"[POMAgent] Detected PO type: {po_type}")
                return po_type
            elif po_type == 'INCOMPLETE':
                print(f"[POMAgent] Incomplete PO type information")
                return 'INCOMPLETE'
            else:
                print(f"[POMAgent] Invalid PO type detected: {po_type}, returning INCOMPLETE")
                return 'INCOMPLETE'
        except Exception as e:
            print(f"[POMAgent] Error detecting PO type: {e}, returning INCOMPLETE")
            return 'INCOMPLETE'

    def _extract_quantity(self, user_instruction: str) -> int:
        """Extract the number of POs to create from user instruction"""
        extract_prompt = f"""Extract the quantity/number of purchase orders to create from this instruction.
        Look for phrases like "create 3 POs", "5 purchase orders", "create 10 pos", etc.
        Return ONLY the number. If no quantity is specified, return 1.

        Instruction: {user_instruction}

        Quantity:"""

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=extract_prompt,
                config=GenerateContentConfig(temperature=0),
            )
            quantity_str = response.text.strip()
            quantity = int(quantity_str)
            return max(1, min(quantity, 20))  # Limit to 1-20 POs
        except:
            return 1

    def _extract_order_number(self, user_instruction: str) -> Optional[str]:
        """Extract order number from user instruction"""
        extract_prompt = f"""Extract the purchase order number from this instruction.
        Look for phrases like "order 123456", "PO 78910", "order number 54321", etc.
        Return ONLY the order number. If no order number is found, return "NONE".

        Instruction: {user_instruction}

        Order Number:"""

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=extract_prompt,
                config=GenerateContentConfig(temperature=0),
            )
            order_number = response.text.strip()
            if order_number and order_number != "NONE":
                return order_number
            return None
        except:
            return None

    def _check_full_details_request(self, user_instruction: str) -> bool:
        """Check if user wants full/complete details"""
        full_keywords = ['full', 'complete', 'entire', 'all', 'detailed', 'everything']
        instruction_lower = user_instruction.lower()
        return any(keyword in instruction_lower for keyword in full_keywords)

    def _format_po_brief(self, po_data: Dict[str, Any]) -> str:
        """Format PO data as brief summary with header, lines, discounts"""
        try:
            lines = []
            lines.append("**🗒️ Purchase Order Summary**")
            lines.append("")

            # Header information
            if isinstance(po_data, dict):
                header = po_data.get('orderHeader', {})
                if header:
                    lines.append("**Order Header:**")
                    lines.append(f"  • Order Number: {header.get('orderNumber', 'N/A')}")
                    lines.append(f"  • Vendor: {header.get('vendorNumber', 'N/A')}")
                    lines.append(f"  • Order Date: {header.get('orderDate', 'N/A')}")
                    lines.append(f"  • Status: {header.get('orderStatus', 'N/A')}")
                    lines.append(f"  • Total Amount: ${header.get('orderAmount', '0.00')}")
                    lines.append("")

            # Order Lines (SKU/Items)
            order_lines = po_data.get('orderLines', [])
            if order_lines:
                lines.append(f"**Order Lines ({len(order_lines)} items):**")
                for idx, line in enumerate(order_lines[:10], 1):  # Show first 10
                    sku = line.get('skuNumber', 'N/A')
                    qty = line.get('quantity', 0)
                    unit_cost = line.get('unitCost', 0.00)
                    lines.append(f"  {idx}. SKU: {sku} | Qty: {qty} | Unit Cost: ${unit_cost}")
                if len(order_lines) > 10:
                    lines.append(f"  ... and {len(order_lines) - 10} more items")
                lines.append("")

            # Discounts
            discounts = po_data.get('discounts', [])
            if discounts:
                lines.append(f"**Discounts ({len(discounts)}):**")
                for disc in discounts:
                    disc_type = disc.get('discountType', 'N/A')
                    disc_amt = disc.get('discountAmount', 0.00)
                    lines.append(f"  • {disc_type}: ${disc_amt}")
                lines.append("")

            # Sub-discounts
            sub_discounts = po_data.get('subDiscounts', [])
            if sub_discounts:
                lines.append(f"**Sub-Discounts ({len(sub_discounts)}):**")
                for sub_disc in sub_discounts:
                    sub_type = sub_disc.get('type', 'N/A')
                    sub_amt = sub_disc.get('amount', 0.00)
                    lines.append(f"  • {sub_type}: ${sub_amt}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error formatting PO brief: {str(e)}\n\nRaw data:\n{json.dumps(po_data, indent=2)}"

    def _format_transmission_summary(self, transmission_data: Dict[str, Any]) -> str:
        """Format transmission data in table format with destination code mapping"""
        try:
            # Check if data has the new table format structure
            if isinstance(transmission_data, dict) and 'latest_10_records' in transmission_data:
                lines = []
                lines.append("## PO Transmission Records")
                lines.append("")

                # Add destination code reference
                lines.append("")

                # Create table header
                lines.append("| Destination | Transaction | Status | Timestamp |")
                lines.append("|-------------|-------------|--------|-----------|")

                # Add table rows from latest_10_records
                for record in transmission_data.get('latest_10_records', []):
                    dest = record.get('Destination', 'N/A')
                    trans = record.get('Transaction', 'N/A')
                    status = record.get('Status', 'N/A')
                    timestamp = record.get('Timestamp', 'N/A')
                    lines.append(f"| {dest} | {trans} | {status} | {timestamp} |")

                lines.append("")

                # Add summary if available
                if 'remaining_summary' in transmission_data:
                    lines.append(transmission_data['remaining_summary'])

                return "\n".join(lines)

            # Fallback for old format - convert to table
            transmissions = transmission_data if isinstance(transmission_data, list) else [transmission_data]
            if transmissions:
                lines = []
                lines.append("## PO Transmission Records")
                lines.append("")
                lines.append("| Destination | Transaction | Status | Timestamp |")
                lines.append("|-------------|-------------|--------|-----------|")

                for transmission in transmissions[:10]:  # Show max 10
                    dest_cd = transmission.get('destCd', 'N/A')
                    ord_msg_trans_cd = transmission.get('ordMsgTransCd', 'N/A')
                    trnsm_stat_ind = transmission.get('trnsmStatInd', 'N/A')
                    last_upd_ts = transmission.get('lastUpdTs', 'N/A')

                    # Translate codes
                    dest_meaning = self._translate_code('destCd', dest_cd)
                    trans_meaning = self._translate_code('ordMsgTransCd', ord_msg_trans_cd)
                    status_meaning = self._translate_code('trnsmStatInd', trnsm_stat_ind)

                    # Format: Code-Meaning
                    dest_display = f"{dest_cd}-{dest_meaning}" if dest_meaning != "Unknown" else str(dest_cd)
                    trans_display = f"{ord_msg_trans_cd}-{trans_meaning}" if trans_meaning != "Unknown" else str(ord_msg_trans_cd)
                    status_display = f"{trnsm_stat_ind}-{status_meaning}" if status_meaning != "Unknown" else str(trnsm_stat_ind)

                    lines.append(f"| {dest_display} | {trans_display} | {status_display} | {last_upd_ts} |")

                lines.append("")
                if len(transmissions) > 10:
                    lines.append(f"*{len(transmissions) - 10} additional records not shown. Total: {len(transmissions)} records.*")

                return "\n".join(lines)

            return "No transmission records found"
        except Exception as e:
            return f"Error formatting transmission summary: {str(e)}\n\nRaw data:\n{json.dumps(transmission_data, indent=2)}"    
            
    def _format_error_summary(self, error_data: Dict[str, Any]) -> str:
        """Format error data with analysis and SKU information"""
        try:
            lines = []
            lines.append("**⚠️ PO Error Summary**")
            lines.append("")

            # Extract error records from the formatted response structure
            if isinstance(error_data, dict):
                # Check if this is a formatted response with latest_10_records
                if 'latest_10_records' in error_data:
                    errors = error_data['latest_10_records']
                    total_count = error_data.get('total_records', len(errors))
                    remaining_count = error_data.get('remaining_records', 0)

                    # Add summary information
                    if total_count > 0:
                        lines.append(f"Found {total_count} total error(s). Showing latest {len(errors)}:")
                        lines.append("")

                    # Display errors in table format
                    if errors:
                        for idx, error_record in enumerate(errors, 1):
                            error_msg = error_record.get('error', 'N/A')
                            resolution = error_record.get('resolution', 'N/A')
                            error_time = error_record.get('error_time', 'N/A')

                            lines.append(f"**Error {idx}:**")
                            lines.append(f"  • **Time:** {error_time}")
                            lines.append(f"  • **Error:** {error_msg}")
                            lines.append(f"  • **Resolution:** {resolution}")
                            lines.append("")

                        # Add remaining count note if applicable
                        if remaining_count > 0:
                            lines.append(f"*... and {remaining_count} more error(s). Total: {total_count} errors.*")
                    else:
                        lines.append("No error records found.")

                elif 'message' in error_data:
                    # Fallback message
                    lines.append(error_data['message'])
                    if 'raw_response' in error_data:
                        lines.append("")
                        lines.append("**Raw Response:**")
                        lines.append(f"```json\n{json.dumps(error_data['raw_response'], indent=2)}\n```")
                else:
                    # Legacy format - try to parse as individual error records
                    errors = [error_data]
                    self._format_legacy_errors(lines, errors)
            elif isinstance(error_data, list):
                # Direct list of error records (legacy)
                self._format_legacy_errors(lines, error_data)
            else:
                lines.append(f"Unexpected error data format: {type(error_data)}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error formatting error summary: {str(e)}\n\nRaw data:\n{json.dumps(error_data, indent=2)}"

    def _format_legacy_errors(self, lines: list, errors: list):
        """Format legacy error structure for backward compatibility"""
        if errors:
            lines.append(f"**Found {len(errors)} error(s):**")
            lines.append("")

            for idx, error in enumerate(errors[:5], 1):  # Show first 5 errors
                error_text = error.get('errorText', error.get('error', 'N/A'))
                sku_number = error.get('skuNumber', '')
                error_ts = error.get('errorTimestamp', error.get('createdDate', error.get('error_time', 'N/A')))

                lines.append(f"**Error {idx}:**")
                if sku_number:
                    lines.append(f"  • SKU: {sku_number}")
                lines.append(f"  • Timestamp: {error_ts}")
                lines.append(f"  • Message: {error_text}")

                # Analyze error text for resolution
                resolution = self._analyze_error_resolution(error_text)
                if resolution:
                    lines.append(f"  • 💡 Resolution: {resolution}")
                lines.append("")

            if len(errors) > 5:
                lines.append(f"*... and {len(errors) - 5} more errors*")

    def _translate_codes_batch(self, code_requests: List[Dict[str, str]]) -> Dict[str, str]:
        """Batch translate multiple codes with a single RAG query (optimized for performance)

        Uses DESTINATION_CODE_MAP for instant destCd lookups before querying RAG.

        Args:
            code_requests: List of dicts with 'type' and 'value' keys
                Example: [{'type': 'destCd', 'value': '36'}, {'type': 'ordMsgTransCd', 'value': '1'}]

        Returns:
            Dict mapping "type:value" to translated meaning
        """
        if not code_requests:
            return {}
        try:
            translations: Dict[str, str] = {}
            rag_requests: List[Dict[str, str]] = []

            # First pass: Use DESTINATION_CODE_MAP for instant destCd lookups
            for req in code_requests:
                key = f"{req['type']}:{req['value']}"
                if req['type'] == 'destCd' and req['value'] in DESTINATION_CODE_MAP:
                    translations[key] = DESTINATION_CODE_MAP[req['value']]
                else:
                    rag_requests.append(req)

            # If all codes resolved from map, return immediately (performance boost)
            if not rag_requests:
                print(f"[POMAgent] Resolved {len(code_requests)} codes from DESTINATION_CODE_MAP (no RAG query needed)")
                return translations

            # Build batch query for remaining codes
            codes_list = "\n".join([
                f"- {req['type']} code {req['value']}"
                for req in rag_requests
            ])

            query = f"""Find the meanings/descriptions for these codes:

{codes_list}

For each code:
1. Search for the section matching the code type
2. Find the code value
3. Return format: "type:value=meaning" (only the meaning text, not the code number)

Examples:
- If destCd 36 is "36 - GCPPUSSUB", return: destCd:36=GCPPUSSUB
- If ordMsgTransCd 1 is "1 - ADD", return: ordMsgTransCd:1=ADD
- If trnsmStatInd TR is "TR - Transmitted", return: trnsmStatInd:TR=Transmitted

Return each result on a new line. If not found, use "Unknown"."""

            # Single RAG query for remaining codes
            result = self._query_rag_corpus(query, similarity_top_k=3)

            if not result or len(result.strip()) < 2:
                # Fallback: return Unknown for remaining codes
                for req in rag_requests:
                    key = f"{req['type']}:{req['value']}"
                    translations[key] = "Unknown"
                return translations
            
            # Parse batch results
            for line in result.split("\n'):
                line = line.strip()
                if '=' in line:
                    # Extract type: value=meaning
                    parts = line.split('=, 1)
                    if len(parts) = 2:
                        key = parts[0].strip()
                        meaning = parts[1].strip().replace('*', "•).replacel*, ")
                        # Clean up "code - meaning" format if present
                        if ' - " in meaning:
                            meaning = meaning.split(" - , 1) [1].strip()
                        translations (key] = meaning if meaning and meaning, lower) I= 'unknown' else "Unknown'
           
           # Fill in any missing translations
            for reg in rag_requests:
                key = f"{req['type']}:{req ['value']}"
                if key not in translations:
                    translations [key] = 'Unknown'
            
            map_count = len(code_requests) - len(ragrequests)
            print(f"[_translate_codes_batch] • Translated {len(code_requests)} codes ({map_count}) from map, {len(rag_requests)} from RAG)")
            return translations

        
        except Exception as e:
            print (f"[_translate_codes_batch] Error in batch translation: {e}")
            # Fallback: return Unknown for all codes not already in translations
            for req in code_requests:
                key = f"{req['type']}:{req['value']}"
                if key not in translations:
                    translations [key] = 'Unknown'
            return translations
       
            
    def _translate_code(self, code_type: str, code_value: str) -> str:
    """Translate code using DESTINATION_CODE_MAP or RAG corpus (optimized)"""
    try:
        # Check DESTINATION_CODE_MAP first for destCd codes (instant lookup)
        if code_type == 'destCd' and code_value in DESTINATION_CODE_MAP:
            return DESTINATION_CODE_MAP[code_value]

        # Build optimized query with specific instructions for RAG
        query = f"""Find the meaning/description for {code_type} code value {code_value}.

Search for:
- Section matching "{code_type}"
- Code value "{code_value}"

Return ONLY the description text after the dash (-), without the code number.
Examples: "36 - GCPPPUBSUB" -> return "GCPPPUBSUB", "1 - ADD" -> return "ADD"
If not found, return "Unknown"."""

        # Single RAG query (no second LLM call)
        result = self._query_rag_corpus(query, similarity_top_k=2)

        if not result or len(result.strip()) < 2:
            return 'Unknown'

        # Clean up any markdown formatting
        result = result.replace('**', '').replace('*', '').strip()

        # Extract just the meaning if format is "code - meaning"
        if ' - ' in result:
            parts = result.split(' - ', 1)
            if len(parts) == 2:
                result = parts[1].strip()

        return result if result and result.lower() != 'unknown' else 'Unknown'
    except Exception as e:
        print(f"[_translate_code] Error translating {code_type}={code_value}: {e}")
        return 'Unknown'

def _analyze_error_resolution(self, error_text: str) -> str:
    """Analyze error text to extract resolution guidance"""
    try:
        analyze_prompt = f"""Analyze this error message and extract actionable resolution steps if present:
Error: {error_text}

If the error contains resolution guidance, extract it concisely. Otherwise, suggest a resolution based on the error.
Keep it brief (1-2 sentences).
"""

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=analyze_prompt,
            config=GenerateContentConfig(temperature=0.3),
        )
        return response.text.strip()
    except:
        return ''

def _analyze_question_and_fetch_data(self, user_question: str) -> Dict[str, Any]:
    """
    Analyze user question, determine what data to fetch, and retrieve it intelligently.
    Handles questions like:
    - What is the vendorPartNumber for SKU 688174 for order 1000498777?
    - How many SKUs are there for order 1000498777?
    - What is the order status for order 1000498777?
    - Can you check transmission for order 1000498777?
    """
    try:
        # Step 1: Use Gemini to understand the question and extract requirements
        analysis_prompt = f"""Analyze this question about a purchase order and extract:
1. Order number (if mentioned)
2. What type of API to call (read_po, read_transmission, read_errors)
3. What specific data to extract from the response
4. What field names to look for

Question: {user_question}

Respond in JSON format:
{{
  "order_number": "extracted order number or null",
  "api_needed": "read_po or read_transmission or read_errors",
  "query_type": "specific_field or count or status or general",
  "target_field": "field name to extract (e.g., vendorPartNumber, skuNumber)",
  "filter_criteria": "any filter like SKU number",
  "needs_rag_translation": true/false
}}
"""

        response = self.client.models.generate_content(
            model=self.model_id,
            contents=analysis_prompt,
            config=GenerateContentConfig(temperature=0),
        )

        # Parse the analysis
        import json as json_module
        analysis_text = response.text.strip()
        # Remove markdown code blocks if present
        if '```json' in analysis_text:
            analysis_text = analysis_text.split('```json')[1].split('```')[0].strip()
        elif '```' in analysis_text:
            analysis_text = analysis_text.split('```')[1].split('```')[0].strip()

        analysis = json_module.loads(analysis_text)

        order_number = analysis.get('order_number')
        api_needed = analysis.get('api_needed', 'read_po')

        if not order_number:
            return {
                'success': False,
                'error': 'Could not identify order number in your question. Please specify the order number.',
                'operation': 'ANALYZE_QUESTION'
            }

        # Step 2: Call the appropriate API
        api_result = None
        if api_needed == 'read_transmission':
            api_result = self.read_po_transmission(order_number)
        elif api_needed == 'read_errors':
            api_result = self.read_po_errors(order_number)
        else: # Default to read_po
            api_result = self.read_purchase_order(order_number, show_full=False)

        if not api_result.get('success'):
            return api_result
            
        
        # Step 3: Use Gemini to answer the question based on the data
        api_data = api_result.get('po_details') or api_result.get('transmission_details') or api_result.get('error_details', {})
        
        answer_prompt = f"""You are a helpful Supply Chain Purchase Order Management Agent.
        
User Question: {user_question}

API Response Data:
{json_module.dumps(api_data, indent=2)}

RAG Knowledge Base (for code translation):
{self.rag_knowledge[:2000]} # Include relevant portion

Instructions:
1. Answer the user's question based on the API response data
2. If codes are present (like orderStatusCode, destCd, etc.), translate them using the RAG knowledge
3. Be specific and direct in your answer
4. Present numbers, SKUs, and details clearly
5. Be polite and professional
6. If the answer cannot be found in the data, say so politely

Please provide a clear, enriched answer:
"""

        answer_response = self.client.models.generate_content(
            model=self.model_id,
            contents=answer_prompt,
            config=GenerateContentConfig(temperature=0.3),
        )

        return {
            'success': True,
            'operation': 'ANALYZE_QUESTION',
            'order_number': order_number,
            'api_called': api_needed,
            'answer': answer_response.text.strip(),
            'raw_data': api_data
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Error analyzing question: {str(e)}',
            'operation': 'ANALYZE_QUESTION'
        }

# Step 3: Use Gemini to answer the question based on the data
        api_data = api_result.get('po_details') or api_result.get('transmission_details') or api_result.get('error_details', {})
        
        answer_prompt = f"""You are a helpful Supply Chain Purchase Order Management Agent.

User Question: {user_question}

API Response Data:
{json_module.dumps(api_data, indent=2)}

RAG Knowledge Base (for code translation):
{self._rag_knowledge[:2000]} # Include relevant portion

Instructions:
1. Answer the user's question based on the API response data
2. If codes are present (like orderStatusCode, destCd, etc.), translate them using the RAG knowledge
3. Be specific and direct in your answer
4. Present numbers, SKUs, and details clearly
5. Be polite and professional
6. If the answer cannot be found in the data, say so politely

Please provide a clear, enriched answer:
"""

        answer_response = self.client.models.generate_content(
            model=self.model_id,
            contents=answer_prompt,
            config=GenerateContentConfig(temperature=0.3),
        )

        return {
            'success': True,
            'operation': 'ANALYZE_QUESTION',
            'order_number': order_number,
            'api_called': api_needed,
            'answer': answer_response.text.strip(),
            'raw_data': api_data
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Error analyzing question: {str(e)}',
            'operation': 'ANALYZE_QUESTION'
        }

def create_purchase_order(self, user_instruction: str) -> Dict[str, Any]:
    """
    Create a purchase order based on natural language instruction.
    
    Args:
        user_instruction: Natural language instruction from user
        
    Returns:
        Dictionary containing the API response and status
    """
    # Initialize progress tracking
    progress_steps: List[str] = []
    
    # Check if PO type information is complete
    completeness = self._check_po_type_completeness(user_instruction)
    
    # If incomplete, provide helpful guidance
    if not completeness.get('has_location_type') or not completeness.get('has_classification'):
        missing_info = []
        if not completeness.get('has_location_type'):
            missing_info.append("location type (BDC, RDC, RDCX, IFC, DFC, TLD, or SDC)")
        if not completeness.get('has_classification'):
            missing_info.append("order classification (Domestic or Import)") 
           
        guidance_msg = f"""I need a bit more information to create your purchase order.

Please specify:
{'- ' + missing_info[0] if len(missing_info) > 0 else ''}
{'- ' + missing_info[1] if len(missing_info) > 1 else ''}

Available PO types:
**Domestic Orders:**
- BDC Domestic - Bulk Distribution Center
- RDC Domestic - Regional Distribution Center
- RDCX Domestic - Regional Distribution Center Cross-dock
- IFC Domestic - Import Flow-through Center
- DFC Domestic - Direct Fulfillment Center

**Import Orders:**
- DFC Import - Direct Fulfillment Center
- TLD Import - Third-party Logistics Distribution
- SDC Import - Supplier Direct Center

Example: "Create a DFC Domestic PO for vendor 12345" or "Create an SDC Import PO for vendor 17404" """

            return {
                'success': False,
                'error': 'Incomplete PO type information',
                'message': guidance_msg,
                'operation': 'CREATE_PO',
                'needs_clarification': True,
                'detected_location': completeness.get('location_type'),
                'detected_classification': completeness.get('classification')
            }

       # Detect PO type from user instruction
        po_type = self._detect_po_type(user_instruction)

        # If still incomplete after detection, ask for clarification
        if po_type == 'INCOMPLETE':
            return {
                'success': False,
                'error': 'Unable to determine PO type',
                'message': 'Please specify both the location type (BDC/RDC/RDCX/IFC/DFC/TLD/SDC) and classification (Domestic/Import).\n\nExample: "Create a DFC Domestic PO" or "Create an SDC Import PO"',
                'operation': 'CREATE_PO',
                'needs_clarification': True
            }

        # Load the appropriate sample based on PO type (on-demand)
        sample_data = self._load_po_type_sample(po_type)
        if sample_data:
            print(f"[POMAgent] Using {po_type} template")
        else:
            # Fallback to empty structure if sample not found
            sample_data = {}
            print(f"[POMAgent] Warning: No sample found for PO type {po_type}, using empty template")

        new_po_request_id = self._generate_po_request_id()

        # Get sample code for reference
        sample_code = self.sample_code.get('create_po_code', '')

        system_prompt = f"""
You are a Purchase Order Management System Agent with advanced natural language understanding.

TASK: Create a new purchase order based on user's natural language instruction.

PO TYPE: {po_type}
This template is specifically designed for {po_type} purchase orders. The sample JSON structure below is optimized for this PO type.

YOUR MISSION:
1. Start with the complete sample JSON structure as your base (this is a {po_type} template)
2. Intelligently analyze the user's instruction to understand what information they're providing
3. Map user's intent to appropriate JSON fields using your understanding of purchase orders
4. Replace ONLY the specific values that the user mentioned - keep everything else from the sample
5. Extract exact values from the user's words
6. Preserve the PO type-specific fields and values from the template

REQUIRED IDs (MUST USE THESE):
- orderHeader.poRequestId: {new_po_request_id}
- orderHeader.srcOrderRefId: {new_po_request_id}
- orderHeader.srcOrdGroupId: {new_po_request_id}

INTELLIGENT FIELD MAPPING:
- Understand the user's intent and find the most appropriate field in the JSON schema
- Examples:
  * "for location 5621" -> find location-related field and set to 5621
  * "vendor 17404" -> find vendor-related field and set to 17404
  * "quantity 100" -> find quantity-related field and set to 100
  * "SKU 1234567" -> find SKU/item number field and set to "1234567"

STRATEGY:
1. Copy the ENTIRE sample JSON structure
2. Set the three required IDs to {new_po_request_id}
3. Intelligently identify and replace only the fields mentioned by the user
4. Keep all other fields exactly as they are in the sample

Sample JSON structure (use as complete base):
{json_module.dumps(sample_data, indent=2)}

RESPONSE: Return ONLY valid JSON matching the structure above, no explanations.
"""

        full_prompt = f"{system_prompt}\n\nUser Instruction: {user_instruction}\n\nGenerate complete JSON:"

        try:
            # Use Gemini to process the request
            config_params = {"temperature": 0.2}
            if self.enable_code_execution:
                config_params["tools"] = [self.code_execution_tool]

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=full_prompt,
                config=GenerateContentConfig(**config_params),
            )

            response_text = response.text if response.text else '{}'

            # Parse JSON from response
            try:
                if response_text and response_text.strip():
                    start_idx = response_text.find('{')
                    end_idx = response_text.rfind('}') + 1
                    if start_idx != -1 and end_idx > start_idx:
                        json_str = response_text[start_idx:end_idx]
                        payload = json_module.loads(json_str)
                    else:
                        payload = json_module.loads(response_text)
                else:
                    payload = sample_data.copy()
            except (json.JSONDecodeError, AttributeError, ValueError):
                payload = sample_data.copy()
                if 'orderHeader' in payload:
                    # Ensure IDs are set
                    payload['orderHeader']['poRequestId'] = new_po_request_id
                    payload['orderHeader']['srcOrderRefId'] = new_po_request_id
                    payload['orderHeader']['srcOrdGroupId'] = new_po_request_id
            # Ensure IDs are set
            payload['orderHeader']['poRequestId'] = new_po_request_id
            payload['orderHeader']['srcOrderRefId'] = new_po_request_id
            payload['orderHeader']['srcOrdGroupId'] = new_po_request_id

            # Get access token
            access_token = self._get_access_token('create_po_api')
            api_config = self.api_config.get('create_po_api', {})
            api_url = api_config.get('api_url', '') + api_config.get('end_point', '') + '?isPubSubFlag=false'

            headers = {'Content-Type': 'application/json'}
            if access_token:
                headers['Authorization'] = f'Bearer {access_token}'

            # Invoke PO Create API
            print(f"[create_purchase_order] POST Request: {api_url}")
            print(f"[create_purchase_order] Request payload: poRequestId={new_po_request_id}")
            api_response = self.http_session.post(api_url, json=payload, headers=headers, timeout=300)
            print(f"[create_purchase_order] API Response Status: {api_response.status_code}")
            
            # Parse response data
            response_data = None
            if api_response.ok:
                try:
                    response_data = api_response.json()
                except:
                    response_data = {'raw_response': api_response.text}
            else:
                # Try to parse error response as JSON
                try:
                    response_data = api_response.json()
                    print(f"[create_purchase_order] Error response: {json.dumps(response_data, indent=2)}")
                except:
                    response_data = {'error': api_response.text, 'status': api_response.status_code}
                    print(f"[create_purchase_order] Error response (text): {api_response.text[:500]}")

            order_number = None
            if api_response.ok and isinstance(response_data, dict):
                order_number = response_data.get('orderNumber')

            # Mark as success only if status code is 200/201
            is_success = api_response.status_code in [200, 201]

            return {
                'success': is_success,
                'status_code': api_response.status_code,
                'po_request_id': new_po_request_id,
                'order_number': order_number,
                'payload': payload,
                'response': response_data,
                'operation': 'CREATE_PO',
                'progress_steps': progress_steps
            }

        except Exception as e:
            error_msg = f"Failed to create PO: {str(e)}"
            progress_steps.append(error_msg)
            return {
                'success': False,
                'error': str(e),
                'po_request_id': new_po_request_id,
                'operation': 'CREATE_PO',
                'progress_steps': progress_steps
            }

    def _translate_status_codes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate status text values to numeric codes according to RAG.
        Maps: cancel/cancelled -> 4, close/closed -> 3, open -> 2, error -> 5
        Also automatically adds cancel reason codes when canceling.
        """
        STATUS_MAP = {
            'cancel': 4,
            'cancelled': 4,
            'canceled': 4,
            'close': 3,
            'closed': 3,
            'open': 2,
            'error': 5
        }

        def translate_value(value):
            """Translate a single value if it's a status text"""
            if isinstance(value, str):
                lower_val = value.strip().lower()
                if lower_val in STATUS_MAP:
                    return STATUS_MAP[lower_val]
            return value

        def process_dict(d):
            """Recursively process dictionary"""
            if not isinstance(d, dict):
                return d

            result = {}
            for key, value in d.items():
                # Check if this is a status field
                if key in ['orderStatusCode', 'orderLineStatusCode', 'orderLinetatusCode']:
                    translated = translate_value(value)
                    result[key] = translated

                    # If status is being set to 4 (cancelled), automatically add cancel reason code
                    if translated == 4:
                        if key == 'orderStatusCode':
                            # Canceling order - add orderCancelReasonCode at orderHeader level
                            if 'orderCancelReasonCode' not in d:
                                result['orderCancelReasonCode'] = 140 # PO header cancel due to line cancel
                                print(f"[_translate_status_codes] Auto-added orderCancelReasonCode=140 for order cancellation")
                        elif key in ['orderLineStatusCode', 'orderLinetatusCode']:
                            # Canceling order line - add orderLineCancelReasonCode at orderLine level
                            if 'orderLineCancelReasonCode' not in d:
                                result['orderLineCancelReasonCode'] = 140 # PO header cancel due to line cancel
                                print(f"[_translate_status_codes] Auto-added orderLineCancelReasonCode=140 for order line cancellation")
                elif isinstance(value, dict):
                    result[key] = process_dict(value)
                elif isinstance(value, list):
                    result[key] = [process_dict(item) if isinstance(item, dict) else item for item in value]
                else:
                    result[key] = value
            return result

        return process_dict(data)

   # def translate_value(value):
            # """Translate a single value if it's a status text"""
            # if isinstance(value, str):
                # lower_val = value.strip().lower()
                # if lower_val in STATUS_MAP:
                    # return STATUS_MAP[lower_val]
            # return value

        # def process_dict(d):
            # """Recursively process dictionary"""
            # if not isinstance(d, dict):
                # return d

            # result = {}
            # for key, value in d.items():
                # # Check if this is a status field
                # if key in ['orderStatusCode', 'orderLineStatusCode', 'orderLinetatusCode']:
                    # translated = translate_value(value)
                    # result[key] = translated

                    # # If status is being set to 4 (cancelled), automatically add cancel reason code
                    # if translated == 4:
                        # if key == 'orderStatusCode':
                            # # Canceling order - add orderCancelReasonCode at orderHeader level
                            # if 'orderCancelReasonCode' not in d:
                                # result['orderCancelReasonCode'] = 140 # PO header cancel due to line cancel
                                # print(f"[_translate_status_codes] Auto-added orderCancelReasonCode=140 for order cancellation")
                        # elif key in ['orderLineStatusCode', 'orderLinetatusCode']:
                            # # Canceling order line - add orderLineCancelReasonCode at orderLine level
                            # if 'orderLineCancelReasonCode' not in d:
                                # result['orderLineCancelReasonCode'] = 140 # PO header cancel due to line cancel
                                # print(f"[_translate_status_codes] Auto-added orderLineCancelReasonCode=140 for order line cancellation")
                # elif isinstance(value, dict):
                    # result[key] = process_dict(value)
                # elif isinstance(value, list):
                    # result[key] = [process_dict(item) if isinstance(item, dict) else item for item in value]
                # else:
                    # result[key] = value
            # return result

        # return process_dict(data)

def update_purchase_order(self, user_instruction: str, order_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Update a purchase order based on natural language instruction.
        Supports two update types:
        1. orderHeader update - updates order header fields only
        2. orderLine update - updates order line fields (requires skuNumber)

        Args:
            user_instruction: Natural language instruction from user
            order_number: Optional order number to update. If not provided, will try to extract from instruction.

        Returns:
            Dictionary containing the API response and status
        """
        progress_steps = []

        # Allowed fields for orderHeader updates
        ALLOWED_HEADER_FIELDS = {
            "orderStatusCode", "origShpgPortCd", "orderCancelReasonCode", "shipmentId",
            "estimatedShipDate", "expectedArrivalDate", "contnTypCd", "receivingLocationNumber",
            "transpModeCd", "factoryId", "finalReceivingLocationNumber", "finalCYETA"
        }

        # Allowed fields for orderLine updates
        ALLOWED_LINE_FIELDS = {
            "orderLineStatusCode", "adjustedOrderQuantity", "unitCostAmount",
            "totalShippedQuantity", "orderLineCancelReasonCode", "packSize",
            "storeBuyPackSize", "costOverRideFlag", "onOrderNotShippedQuantity", "totalReceivedQuantity"
        }

        # Step 1: Extract order number and SKU if not provided
        if not order_number:
            extract_prompt = f"""Extract the order number or PO number from this instruction.
            Look for patterns like: PO#12345, order 12345, PO 12345, order number 12345
            Return only the number, nothing else.
            If no order number found, return NONE.

            Instruction: {user_instruction}
            Order Number:"""

            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=extract_prompt,
                    config=GenerateContentConfig(temperature=0),
                )
                extracted = response.text.strip()
                if extracted.upper() != 'NONE':
                    order_number = extracted
                else:
                    error_msg = 'No order number found in instruction. Please specify PO number to update.'
                    progress_steps.append(error_msg)
                    return {
                        'success': False,
                        'error': error_msg,
                        'operation': 'UPDATE_PO',
                        'progress_steps': progress_steps
                    }

            except Exception as e:
                error_msg = f'Could not extract order number: {str(e)}'
                progress_steps.append(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'operation': 'UPDATE_PO',
                    'progress_steps': progress_steps
                }
                
        # Step 2: Determine update type (orderHeader vs orderLine)
        detect_type_prompt = f"""Analyze this purchase order update instruction and determine the update type.

        Instruction: {user_instruction}

        If the user wants to update:
        - Order-level fields like status, ship date, location, port, shipment, factory, arrival date, etc. -> Return "HEADER"
        - Line-level fields like SKU, quantity, cost, pack size, shipped quantity, received quantity, etc. -> Return "LINE"
        - If a SKU number is mentioned -> Return "LINE"

        Return ONLY one word: "HEADER" or "LINE"
        """

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=detect_type_prompt,
                config=GenerateContentConfig(temperature=0),
            )
            update_type = response.text.strip().upper()

            if update_type not in ['HEADER', 'LINE']:
                update_type = 'HEADER'  # Default to HEADER
        
        except:
            update_type = 'HEADER'  # Default to HEADER on error

        print(f"[update_purchase_order] Detected update type: {update_type}")

        # Step 3: Extract SKU number if LINE update
        sku_number = None
        if update_type == 'LINE':
            extract_sku_prompt = f"""Extract the SKU number from this instruction.
            Look for patterns like: SKU 12345, sku 12345, item 12345, product 12345
            Return only the number, nothing else.
            If no SKU found, return NONE.

            Instruction: {user_instruction}
            SKU Number:"""

            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=extract_sku_prompt,
                    config=GenerateContentConfig(temperature=0),
                )
                sku_extracted = response.text.strip()
                if sku_extracted.upper() != 'NONE':
                    sku_number = sku_extracted
                else:
                    error_msg = 'x For orderline update, both orderNumber and skuNumber are required. Please specify SKU.'
                    progress_steps.append(error_msg)
                    return {
                        'success': False,
                        'error': error_msg,
                        'operation': 'UPDATE_PO',
                        'progress_steps': progress_steps
                    }
            except Exception as e:
                error_msg = f'x Could not extract SKU number: {str(e)}'
                progress_steps.append(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'operation': 'UPDATE_PO',
                    'progress_steps': progress_steps
                }

        # Step 4: Build the update payload based on type
        try:
            if update_type == 'HEADER':
                # Use orderHeader sample
                header_sample_path = self.base_dir / 'resources' / 'samples' / 'update_po_orderHeader_api_input_sample.json'
                with open(header_sample_path, 'r') as f:
                    sample_data = json.load(f)

                system_prompt = f"""You are a Purchase Order Management System Agent.

                TASK: Create orderHeader update payload for order #{order_number}.

                ALLOWED FIELDS (you can ONLY update these fields in orderHeader):
                {', '.join(sorted(ALLOWED_HEADER_FIELDS))}

                CRITICAL RULES:
                1. Extract field values from user instruction: "{user_instruction}"
                2. Map user's words to allowed field names (e.g., "status" -> orderStatusCode, "ship date" -> estimatedShipDate)
                3. Include ONLY the allowed fields mentioned by the user
                4. For dates, use format: "YYYY-MM-DD" (e.g., "2026-09-01")
                5. ALWAYS include: orderNumber, lastUpdateSystemUserId, lastUpdateProgramId
                6. Set lastUpdateSystemUserId = "POM_AGENT"
                7. Set lastUpdateProgramId = "POM_AGENT"
                8. DO NOT include any other fields beyond the allowed list

                Sample structure:
                {json.dumps(sample_data, indent=2)}

                Return ONLY valid JSON array format: [{{ "orderHeader": {{...}}}}]
                No explanations, no markdown, just JSON."""

            else:  # LINE update
                # Use orderline sample
                line_sample_path = self.base_dir / 'resources' / 'samples' / 'update_po_orderLine_api_input_sample.json'
                with open(line_sample_path, 'r') as f:
                    sample_data = json.load(f)

                system_prompt = f"""You are a Purchase Order Management System Agent.

                TASK: Create orderLine update payload for order #{order_number}, SKU #{sku_number}.

                ALLOWED FIELDS (you can ONLY update these fields in orderLines):
                {', '.join(sorted(ALLOWED_LINE_FIELDS))}

                CRITICAL RULES:
                1. Extract field values from user instruction: "{user_instruction}"
                2. Map user's words to allowed field names (e.g., "quantity" -> adjustedOrderQuantity, "cost" -> unitCostAmount)
                3. Include ONLY the allowed fields mentioned by the user in orderLines
                4. ALWAYS include orderHeader with: orderNumber, lastUpdateSystemUserId, lastUpdateProgramId
                5. ALWAYS include orderLines array with: skuNumber + user-specified allowed fields
                6. Set lastUpdateSystemUserId = "POM_AGENT" (NOTE: This will be automatically changed to "RECPT_INTG_SVC" if updating totalReceivedQuantity)
                7. Set lastUpdateProgramId = "POM_AGENT"
                8. DO NOT include any other fields beyond the allowed list

                Sample structure:
                {json.dumps(sample_data, indent=2)}

                Return ONLY valid JSON array format: [{{ "orderHeader": {{...}}, "orderLines": [{{
                ...}}]}}]
                No explanations, no markdown, just JSON."""

            full_prompt = f"{system_prompt}\n\nUser Instruction: {user_instruction}\n\nGenerate JSON:"

            # Use Gemini to build the payload
            config_params = {"temperature": 0.1}
            if self.enable_code_execution:
                config_params["tools"] = [self.code_execution_tool]
            
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=full_prompt,
                config=GenerateContentConfig(**config_params),
            )
            
            response_text = response.text if response.text else '{}'

            # Parse JSON from response
            try:
                # Extract JSON from markdown code blocks if present
                if '```json' in response_text:
                    start = response_text.find('```json') + 7
                    end = response_text.find('```', start)
                    response_text = response_text[start:end].strip()
                elif '```' in response_text:
                    start = response_text.find('```') + 3
                    end = response_text.find('```', start)
                    response_text = response_text[start:end].strip()
                
                # Find JSON object/array
                start_idx = response_text.find('[') if '[' in response_text else response_text.find('{')
                if start_idx == -1:
                    raise ValueError("No JSON found in response")
                
                end_idx = response_text.rfind(']') + 1 if '[' in response_text else response_text.rfind('}') + 1
                json_str = response_text[start_idx:end_idx]
                payload = json.loads(json_str)

            except (json.JSONDecodeError, ValueError) as e:
                print(f"[update_purchase_order] JSON parse error: {e}")
                # Use sample as fallback
                payload = sample_data.copy()

            # Ensure payload is an array
            if not isinstance(payload, list):
                payload = [payload]

            # Step 5: Enforce required fields and validation
            if payload and len(payload) > 0:
                item = payload[0]
                
                # Ensure orderHeader exists
                if 'orderHeader' not in item:
                    item['orderHeader'] = {}

                # Set required fields
                item['orderHeader']['orderNumber'] = int(order_number) if order_number.isdigit() else order_number
                
                # Check if updating totalReceivedQuantity - if so, use special system user ID
                updating_received_qty = False
                if update_type == 'LINE' and 'orderLines' in item and item['orderLines']:
                    for line in item['orderLines']:
                        if 'totalReceivedQuantity' in line:
                            updating_received_qty = True
                            break
                
                # Set lastUpdateSystemUserId based on what's being updated
                if updating_received_qty:
                    item['orderHeader']['lastUpdateSystemUserId'] = 'RECPT_INTG_SVC'
                    print(f"[update_purchase_order] Detected totalReceivedQuantity update - using lastUpdateSystemUserId='RECPT_INTG_SVC'")
                else:
                    item['orderHeader']['lastUpdateSystemUserId'] = 'POM_AGENT'
                
                item['orderHeader']['lastUpdateProgramId'] = 'POM_AGENT'

                # Filter orderHeader to only allowed fields
                filtered_header = {
                    k: v for k, v in item['orderHeader'].items()
                    if k in ALLOWED_HEADER_FIELDS or k in ['orderNumber', 'lastUpdateSystemUserId', 'lastUpdateProgramId']
                }
                item['orderHeader'] = filtered_header
                
                # Handle orderLines for LINE updates
                if update_type == 'LINE':
                    if 'orderLines' not in item or not item['orderLines']:
                        item['orderLines'] = [{}]
                    
                    # Set SKU and filter allowed fields
                    for line in item['orderLines']:
                        line['skuNumber'] = int(sku_number) if sku_number.isdigit() else sku_number
                        filtered_line = {k: v for k, v in line.items() if k in ALLOWED_LINE_FIELDS or k == 'skuNumber'}
                        line.clear()
                        line.update(filtered_line)
                else:
                    # For HEADER updates, remove orderlines if present
                    if 'orderLines' in item:
                        del item['orderLines']

            # Step 5.5: Translate status text to numeric codes (cancel->4, close->3, open->2, error->5)
            payload = [self._translate_status_codes(item) for item in payload]

            # Step 6: Call API
            access_token = self._get_access_token('update_po_api')
            api_config = self.api_config.get('update_po_api', {})
            api_url = api_config.get('api_url', '') + api_config.get('end_point', '')

            headers = {'Content-Type': 'application/json'}
            if access_token:
                headers['Authorization'] = f'Bearer {access_token}'
                print(f"[update_purchase_order] Using Bearer token authentication")
            else:
                print(f"[update_purchase_order] No authentication token (API not secured or token unavailable)")

            print(f"[update_purchase_order] PUT Request: {api_url}")
            print(f"[update_purchase_order] Update type: {update_type}, orderNumber: {order_number}" + (f", skuNumber: {sku_number}" if sku_number else ""))
            print(f"[update_purchase_order] Input Payload:")
            print(json.dumps(payload, indent=2))

            # Invoke API
            api_response = self.http_session.put(api_url, json=payload, headers=headers, timeout=300)
            print(f"[update_purchase_order] API Response Status: {api_response.status_code}")

            # Parse response
            try:
                response_data = api_response.json()
                print(f"[update_purchase_order] Output Payload:")
                print(json.dumps(response_data, indent=2))
            except:
                response_data = {'error': api_response.text, 'status_code': api_response.status_code}
                print(f"[update_purchase_order] Output Payload (error):")
                print(json.dumps(response_data, indent=2))

            return {
                'success': api_response.status_code in [200, 201, 204],
                'status_code': api_response.status_code,
                'order_number': order_number,
                'sku_number': sku_number,
                'update_type': update_type,
                'payload': payload,
                'response': response_data,
                'operation': 'UPDATE_PO',
                'progress_steps': progress_steps
            }

        except Exception as e:
            error_msg = f"x Failed to update PO: {str(e)}"
            progress_steps.append(error_msg)
            print(f"[update_purchase_order] EXCEPTION: {error_msg}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'order_number': order_number,
                'operation': 'UPDATE_PO',
                'progress_steps': progress_steps
            }

    def read_purchase_order(self, order_number: str, show_full: bool = False) -> Dict[str, Any]:
        """
        Read/Check purchase order details by order number.

        Args:
            order_number: The purchase order number to retrieve
            show_full: If True, return complete details; if False, return brief summary

        Returns:
            Dictionary with PO details and status
        """
        progress_steps = []

        try:
            print(f"\n[read_purchase_order] ========== Starting READ_PO for order: {order_number} ==========")

            # Step 1: Get API configuration
            api_config = self.api_config.get('read_po_api', {})

            if not api_config:
                error_msg = 'read_po_api configuration not found'
                print(f"[read_purchase_order] ERROR: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg,
                    'operation': 'READ_PO'
                }
            
            print(f"[read_purchase_order] API config loaded: is_secured={api_config.get('is_secured')}")

            # Get access token (this will call token API if secured)
            print(f"[read_purchase_order] Getting access token...")
            access_token = self._get_access_token('read_po_api')

            if api_config.get('is_secured') and not access_token:
                error_msg = 'x Failed to obtain access token for secured API'
                print(f"[read_purchase_order] ERROR: {error_msg}")
                progress_steps.append(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'operation': 'READ_PO',
                    'progress_steps': progress_steps
                }

            # Build API URL
            api_url = api_config.get('api_url', '') + api_config.get('end_point', '').format(orderNumber=order_number)
            print(f"[read_purchase_order] Calling READ PO API: {api_url}")

            headers = {'Content-Type': 'application/json'}
            if access_token:
                headers['Authorization'] = f'Bearer {access_token}'
                print(f"[read_purchase_order] Using Bearer token authentication")
            else:
                print(f"[read_purchase_order] No authentication token (API not secured or token unavailable)")

            # Invoke Read PO API
            print(f"[read_purchase_order] GET Request: {api_url}")
            api_response = self.http_session.get(api_url, headers=headers, timeout=300)

            print(f"[read_purchase_order] API Response Status: {api_response.status_code}")

            # Parse response
            try:
                response_data = api_response.json()
            except Exception as parse_error:
                print(f"[read_purchase_order] Failed to parse JSON: {str(parse_error)}")
                response_data = {'error': api_response.text, 'status_code': api_response.status_code}
            
            # Check for API errors
            if api_response.status_code != 200:
                error_msg = f"x API returned status {api_response.status_code}: {response_data.get('error', api_response.text)}"
                print(f"[read_purchase_order] ERROR: {error_msg}")
                progress_steps.append(error_msg)
                return {
                    'success': False,
                    'status_code': api_response.status_code,
                    'error': error_msg,
                    'order_number': order_number,
                    'operation': 'READ_PO',
                    'progress_steps': progress_steps
                }

            return {
                'success': True,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'po_details': response_data,
                'show_full': show_full,
                'operation': 'READ_PO'
            }

        except Exception as e:
            error_msg = f"x Exception occurred: {str(e)}"
            print(f"[read_purchase_order] EXCEPTION: {error_msg}")
            import traceback
            traceback.print_exc()
            progress_steps.append(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'order_number': order_number,
                'operation': 'READ_PO',
                'progress_steps': progress_steps
            }

    def read_po_transmission(self, order_number: str) -> Dict[str, Any]:
        """
        Read/Check purchase order transmission details.

        Args:
            order_number: The purchase order number to check transmission for
        
        Returns:
            Dictionary with PO transmission details (formatted summary)
        """
        print(f"\n[read_po_transmission] ========== Starting READ_PO_TRANSMISSION for order: {order_number} ==========")
        progress_steps = []

        try:
            # Get API configuration
            api_config = self.api_config.get('read_po_transmission_api', {})
            print(f"[read_po_transmission] API config loaded: is_secured={api_config.get('is_secured')}")

            if not api_config:
                error_msg = 'x read_po_transmission_api configuration not found'
                print(f"[read_po_transmission] ERROR: {error_msg}")
                progress_steps.append(error_msg)
                return {
                    'success': False,
                    'error': error_msg,
                    'operation': 'READ_PO_TRANSMISSION',
                'progress_steps': progress_steps
            }

        # Get access token (this will call token API if secured)
        print(f"[read_po_transmission] Getting access token...")
        access_token = self._get_access_token('read_po_transmission_api')

        if api_config.get('is_secured') and not access_token:
            error_msg = 'x Failed to obtain access token for secured API'
            print(f"[read_po_transmission] ERROR: {error_msg}")
            progress_steps.append(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'operation': 'READ_PO_TRANSMISSION',
                'progress_steps': progress_steps
            }

        # Build API URL
        api_url = api_config.get('api_url', '') + api_config.get('end_point', '').format(orderNumber=order_number)
        print(f"[read_po_transmission] Calling READ PO TRANSMISSION API: {api_url}")

        headers = {'Content-Type': 'application/json'}
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            print(f"[read_po_transmission] Using Bearer token authentication")
        else:
            print(f"[read_po_transmission] No authentication token")

        # Invoke Read PO Transmission API
        print(f"[read_po_transmission] GET Request: {api_url}")
        api_response = self.http_session.get(api_url, headers=headers, timeout=300)
        print(f"[read_po_transmission] API Response Status: {api_response.status_code}")

        # Parse response
        try:
            response_data = api_response.json()
            print(f"[read_po_transmission] Response parsed successfully. Type: {type(response_data)}")
            if isinstance(response_data, dict):
                print(f"[read_po_transmission] Response is dict with keys: {list(response_data.keys())}")
            elif isinstance(response_data, list):
                print(f"[read_po_transmission] Response is list with {len(response_data)} items")
            if response_data:
                print(f"[read_po_transmission] First item keys: {list(response_data[0].keys()) if isinstance(response_data[0], dict) else 'not a dict'}")
        except Exception as e:
            print(f"[read_po_transmission] ERROR: Failed to parse JSON response: {e}")
            response_data = {'error': api_response.text, 'status_code': api_response.status_code}

        # Handle non-200 responses
        if api_response.status_code == 404:
            return {
                'success': False,
                'status_code': 404,
                'order_number': order_number,
                'error': f'No transmission records found for order {order_number}',
                'operation': 'READ_PO_TRANSMISSION'
            }
        elif api_response.status_code != 200:
            return {
                'success': False,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'error': f'API returned status {api_response.status_code}: {response_data.get("error", "Unknown error")}',
                'operation': 'READ_PO_TRANSMISSION'
            }

        # Format transmission details: show latest 10 records in table format
        all_records = None

        # Handle both list and dict responses
        if isinstance(response_data, list):
            print(f"[read_po_transmission] Response is a list with {len(response_data)} records")
            all_records = response_data
        elif isinstance(response_data, dict):
            print(f"[read_po_transmission] Response data keys: {list(response_data.keys())}")

            # Look for error records in the response
            for key in ['transmissions', 'transmission', 'records', 'data', 'items', 'poTransmissions']:
                if key in response_data and isinstance(response_data[key], list):
                    print(f"[read_po_transmission] Found records under key: '{key}'")
                    all_records = response_data[key]
                    break

        if all_records:
            total_count = len(all_records)
            print(f"[read_po_transmission] Total records found: {total_count}")

            # Get latest 10 records (assuming latest are first, otherwise reverse)
            latest_10 = all_records[:10]
            remaining_count = max(0, total_count - 10)

            # Extract Destination, Transaction, Status, Timestamp for latest 10 in table format
            # OPTIMIZED: Collect all codes first, then batch translate with single RAG query

            # Step 1: Extract all raw codes from all records
            raw_records = []
            code_requests = []

            for idx, record in enumerate(latest_10):
                print(f"[read_po_transmission] Processing record {idx+1}: {list(record.keys())}")
                raw_record = {}

                # Extract raw Destination code
                dest_cd = (record.get('destCd') or record.get('destination') or
                           record.get('destinationCode') or record.get('destinationName') or
                           record.get('dest'))
                raw_record['dest_cd'] = dest_cd
                if dest_cd:
                    code_requests.append({'type': 'destCd', 'value': str(dest_cd)})

                # Extract raw Transaction code
                ord_msg_trans_cd = (record.get('ordMsgTransCd') or record.get('transactionCode') or
                                    record.get('transaction') or record.get('transactionId') or
                                    record.get('transmissionId') or record.get('txn'))
                raw_record['ord_msg_trans_cd'] = ord_msg_trans_cd
                if ord_msg_trans_cd:
                    code_requests.append({'type': 'ordMsgTransCd', 'value': str(ord_msg_trans_cd)})

                # Extract raw Status code
                trnsm_stat_ind = (record.get('trnsmStatInd') or record.get('transmissionStatus') or
                                  record.get('status') or record.get('statusCode') or
                                  record.get('state'))
                raw_record['trnsm_stat_ind'] = trnsm_stat_ind
                if trnsm_stat_ind:
                    code_requests.append({'type': 'trnsmStatInd', 'value': str(trnsm_stat_ind)})

                # Extract Timestamp
                timestamp = (record.get('lastUpdTs') or record.get('lastUpdateTimestamp') or
                             record.get('timestamp') or record.get('lastUpdated') or
                             record.get('updatedAt') or record.get('transmissionTime'))
                raw_record['timestamp'] = timestamp or 'N/A'

                raw_records.append(raw_record)

            # Step 2: Single batch RAG query for all codes at once
            print(f"[read_po_transmission] Batch translating {len(code_requests)} codes with single RAG query")
            translations = self._translate_codes_batch(code_requests)

            # Step 3: Build table records using cached translations
            table_records = []
            for idx, raw_record in enumerate(raw_records):
                row = {}

                # Apply Destination translation
                dest_cd = raw_record['dest_cd']
                if dest_cd:
                    dest_key = f"destCd:{dest_cd}"
                    dest_meaning = translations.get(dest_key, 'Unknown')
                    row['Destination'] = f"{dest_cd}-{dest_meaning}" if dest_meaning != "Unknown" else str(dest_cd)
                else:
                    row['Destination'] = 'N/A'

                # Apply Transaction translation
                ord_msg_trans_cd = raw_record['ord_msg_trans_cd']
                if ord_msg_trans_cd:
                    trans_key = f"ordMsgTransCd:{ord_msg_trans_cd}"
                    trans_meaning = translations.get(trans_key, 'Unknown')
                    row['Transaction'] = f"{ord_msg_trans_cd}-{trans_meaning}" if trans_meaning != "Unknown" else str(ord_msg_trans_cd)
                else:
                    row['Transaction'] = 'N/A'

                # Apply Status translation
                trnsm_stat_ind = raw_record['trnsm_stat_ind']
                if trnsm_stat_ind:
                    status_key = f"trnsmStatInd:{trnsm_stat_ind}"
                    status_meaning = translations.get(status_key, 'Unknown')
                    row['Status'] = f"{trnsm_stat_ind}-{status_meaning}" if status_meaning != "Unknown" else str(trnsm_stat_ind)
                else:
                    row['Status'] = 'N/A'

                row['Timestamp'] = raw_record['timestamp']
                table_records.append(row)

            # Create clean response with table format
            formatted_response = {
                'order_number': order_number,
                'table_format': True,
                'latest_10_records': table_records,
                'total_records': total_count,
                'remaining_records': remaining_count
            }

            if remaining_count > 0:
                formatted_response['remaining_summary'] = f"{remaining_count} additional transmission records not shown. Total: {total_count} records for order {order_number}."
            else:
                formatted_response['remaining_summary'] = f"Showing all {total_count} transmission record{'s' if total_count != 1 else ''} for order {order_number}."

            return {
                'success': True,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'transmission_details': formatted_response,
                'operation': 'READ_PO_TRANSMISSION'
            }

        # Fallback if no records found in expected structure
        return {
            'success': True,
            'status_code': api_response.status_code,
            'order_number': order_number,
            'transmission_details': {'message': 'No transmission records found in response', 'raw_response': response_data},
            'operation': 'READ_PO_TRANSMISSION'
        }

    except Exception as e:
        error_msg = f"x Failed to read transmission: {str(e)}"
        progress_steps.append(error_msg)
        return {
            'success': False,
            'error': str(e),
            'order_number': order_number,
            'operation': 'READ_PO_TRANSMISSION',
            'progress_steps': progress_steps
        }

def read_po_errors(self, order_number: str) -> Dict[str, Any]:
    """
    Read/Check purchase order error details.

    Args:
        order_number: The purchase order number to check errors for

    Returns:
        Dictionary with PO error details (formatted summary with resolution)
    """
    print(f"\n[read_po_errors] ========== Starting READ_PO_ERRORS for order: {order_number} ==========")
    progress_steps = []

    try:
        # Get API configuration
        api_config = self.api_config.get('read_po_errors_api', {})
        print(f"[read_po_errors] API config loaded: is_secured={api_config.get('is_secured')}")

        if not api_config:
            error_msg = 'x read_po_errors_api configuration not found'
            print(f"[read_po_errors] ERROR: {error_msg}")
            progress_steps.append(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'operation': 'READ_PO_ERRORS',
                'progress_steps': progress_steps
            }

        # Get access token (this will call token API if secured)
        print(f"[read_po_errors] Getting access token...")
        access_token = self._get_access_token('read_po_errors_api')

        if api_config.get('is_secured') and not access_token:
            error_msg = 'x Failed to obtain access token for secured API'
            print(f"[read_po_errors] ERROR: {error_msg}")
            progress_steps.append(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'operation': 'READ_PO_ERRORS',
                'progress_steps': progress_steps
            }

        # Build API URL
        api_url = api_config.get('api_url', '') + api_config.get('end_point', '').format(orderNumber=order_number)
        print(f"[read_po_errors] Calling READ PO ERRORS API: {api_url}")

        headers = {'Content-Type': 'application/json'}
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
            print(f"[read_po_errors] Using Bearer token authentication")
        else:
            print(f"[read_po_errors] No authentication token")

        # Invoke Read PO Errors API
        print(f"[read_po_errors] GET Request: {api_url}")
        api_response = self.http_session.get(api_url, headers=headers, timeout=300)
        print(f"[read_po_errors] API Response Status: {api_response.status_code}")

        # Parse response
        try:
            response_data = api_response.json()
        except:
            print(f"[read_po_errors] ERROR: Failed to parse JSON response")
            response_data = {'error': api_response.text, 'status_code': api_response.status_code}

        # Handle non-200 responses
        if api_response.status_code == 404:
            return {
                'success': False,
                'status_code': 404,
                'order_number': order_number,
                'error': f'No error records found for order {order_number}',
                'operation': 'READ_PO_ERRORS'
            }

        elif api_response.status_code != 200:
            return {
                'success': False,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'error': f'API returned status {api_response.status_code}: {response_data.get("error", "Unknown error")}',
                'operation': 'READ_PO_ERRORS'
            }

        # Format error details: show latest 10 records in table format
        all_records = None

        # Handle both list and dict responses
        if isinstance(response_data, list):
            print(f"[read_po_errors] Response is a list with {len(response_data)} records")
            all_records = response_data
        elif isinstance(response_data, dict):
            print(f"[read_po_errors] Response data keys: {list(response_data.keys())}")

            # Look for error records in the response
            for key in ['errors', 'error', 'errorRecords', 'records', 'data', 'items', 'poErrors']:
                if key in response_data and isinstance(response_data[key], list):
                    print(f"[read_po_errors] Found records under key: '{key}'")
                    all_records = response_data[key]
                    break

        if all_records:
            total_count = len(all_records)
            print(f"[read_po_errors] Total records found: {total_count}")

            # Get latest 10 records (assuming latest are first, otherwise reverse)
            latest_10 = all_records[:10]
            remaining_count = max(0, total_count - 10)

            # Parse error_text into error and resolution, rename createTimestamp to error_time
            table_records = []
            for record in latest_10:
                print(f"[read_po_errors] Processing record: {list(record.keys())}")
                row = {}

                # Parse error_text into error and resolution
                error_text = record.get('errorText', record.get('error_text', record.get('message', record.get('errorMessage', ''))))
                print(f"[read_po_errors] Extracted error_text: {error_text[:100] if error_text else 'NONE'}")

                if error_text:
                    # Try to split error_text into error and resolution
                    # Common patterns: "Error: ... Resolution: ...", "Error - ... Fix: ..."
                    if 'Resolution:' in error_text:
                        parts = error_text.split('Resolution:', 1)
                        row['error'] = parts[0].replace('Error:', '').strip()
                        row['resolution'] = parts[1].strip()
                    elif 'Fix:' in error_text:
                        parts = error_text.split('Fix:', 1)
                        row['error'] = parts[0].replace('Error:', '').strip()
                        row['resolution'] = parts[1].strip()
                    elif 'Solution:' in error_text:
                        parts = error_text.split('Solution:', 1)
                        row['error'] = parts[0].replace('Error:', '').strip()
                        row['resolution'] = parts[1].strip()
                    else:
                        # If no clear separator, put entire text in error
                        row['error'] = error_text.strip()
                        row['resolution'] = 'N/A'
                else:
                    row['error'] = 'N/A'
                    row['resolution'] = 'N/A'

                # Rename createTimestamp to error_time
                if 'createTimestamp' in record:
                    row['error_time'] = record['createTimestamp']
                elif 'created_timestamp' in record:
                    row['error_time'] = record['created_timestamp']
                elif 'createdTimestamp' in record:
                    row['error_time'] = record['createdTimestamp']
                elif 'timestamp' in record:
                    row['error_time'] = record['timestamp']
                elif 'createdDate' in record:
                    row['error_time'] = record['createdDate']
                elif 'errorTime' in record:
                    row['error_time'] = record['errorTime']
                else:
                    row['error_time'] = 'N/A'

                table_records.append(row)

            # Create clean response with table format
            formatted_response = {
                'table_format': True,
                'latest_10_records': table_records,
                'total_count': total_count,
                'remaining_records': remaining_count
            }

            if remaining_count > 0:
                formatted_response['remaining_summary'] = f"{remaining_count} additional error records not shown. Total: {total_count} error records."
            else:
                formatted_response['remaining_summary'] = f"Showing all {total_count} error record{'s' if total_count != 1 else ''}."

           return {
                'success': True,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'error_details': formatted_response,
                'operation': 'READ_PO_ERRORS'
            }
           # Fallback if no records found in expected structure
            return {
                'success': True,
                'status_code': api_response.status_code,
                'order_number': order_number,
                'error_details': {'message': 'No error records found in response', 'raw_response': response_data},
                'operation': 'READ_PO_ERRORS'
            }

    except Exception as e:
        error_msg = f"x Failed to read errors: {str(e)}"
        progress_steps.append(error_msg)
        return {
            'success': False,
            'error': str(e),
            'order_number': order_number,
            'operation': 'READ_PO_ERRORS',
            'progress_steps': progress_steps
        }

    def process_natural_language_request(self, user_input: str) -> Dict[str, Any]:
        """
        Process natural language request and determine the appropriate action.

        Args:
            user_input: Natural language input from user

        Returns:
            Dictionary containing the action result
        """
        classification_prompt = f"""
Classify this request into one category:
- GREETING: Greetings like "Hi", "Hello", "Hey", "How are you"
- HELP: Questions about capabilities like "What can you do?", "Help", "What are your capabilities?"
- CREATE_PO: Create a new purchase order
- UPDATE_PO: Update an existing purchase order
- ANALYZE_QUESTION: Specific questions about PO data including transmission and error checks when order number is mentioned (e.g., "What is the vendor for order X?", "How many SKUs?", "What is the status of PO X?")
- READ_PO: Simple read/display purchase order details (keywords: "read", "show", "display" + "PO" without specific questions)
- KNOWLEDGE_QUERY: Questions about POM codes, status meanings, transaction codes, distribution center types, code definitions, etc.
Examples: "What is status 2?", "What does order status 5 mean?", "Explain transaction code 7", "What are the cancel reason codes?", "Tell me about destination codes"
- ANALYZE_DATA: Analyze historical data or generate reports (BigQuery)
- CONVERSATION: Any other conversational or general questions

IMPORTANT:
- If the user mentions an order NUMBER AND asks about transmission or errors, classify as ANALYZE_QUESTION.
- If the user asks about code meanings, statuses, or definitions WITHOUT a specific order number, classify as KNOWLEDGE_QUERY.

Request: {user_input}

Respond with only the category name.
"""

    try:
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=classification_prompt,
            config=GenerateContentConfig(temperature=0),
        )
        
        intent = response.text.strip().upper()

        if 'GREETING' in intent:
            return {'success': True, 'message': 'Hi! How can I help you with your purchase orders today?', 'operation': 'GREETING'}
        elif 'HELP' in intent:
            help_message = (
                "I am your intelligent Supply Chain Purchase Order Management Agent. I can help you with:\n\n"
                "**Core Operations:**\n"
                "- Create new purchase orders (8 PO types: BDC/RDC/RDCX/IFC/DFC Domestic, DFC/TLD/SDC Import)\n"
                "- Update existing purchase orders\n"
                "- Read/check PO details\n"
                "- Check PO transmission status\n"
                "- View PO error details\n\n"
                "**Intelligent Analysis:**\n"
                "- Answer specific questions about your orders (e.g., 'What is the vendor for order 123456?')\n"
                "- Count SKUs, items, or other elements ('How many SKUs in order 123456?')\n"
                "- Check order status with enriched explanations ('What is the status of order 123456?')\n"
                "- Analyze transmission details with code translations\n"
                "- Extract specific field values (vendorPartNumber, SKU details, etc.)\n\n"
                "**How I Help:**\n"
                "- I translate codes using my knowledge base (status codes, destination codes, etc.)\n"
                "- I provide clear, enriched answers with context\n"
                "- I can fetch and analyze data intelligently to answer your questions\n"
                "- If I need clarification, I will ask politely\n\n"
                "Try asking me specific questions about your orders!"
            )
            return {'success': True, 'message': help_message, 'operation': 'HELP'}
        
        elif 'CONVERSATION' in intent:
            # For general conversation, use Gemini to respond naturally
            conv_prompt = f"You are a helpful Supply Chain PO management assistant. Respond to this message naturally and briefly: {user_input}"
            conv_response = self.client.models.generate_content(
                model=self.model_id,
                contents=conv_prompt,
                config=GenerateContentConfig(temperature=0.7),
            )
            return {'success': True, 'message': conv_response.text.strip(), 'operation': 'CONVERSATION'}
            
        elif 'CREATE' in intent:
            # Extract quantity of POs to create
            quantity = self._extract_quantity(user_input)
            
            if quantity > 1:
                # Create multiple POs
                results = []
                for i in range(quantity):
                    result = self.create_purchase_order(user_input)
                    if result.get('success'):
                        results.append(result)
                    else:
                        # If one fails, return the error
                        return result
                        
                # Return combined results
                return {
                    'success': True,
                    'operation': 'CREATE_MULTIPLE_PO',
                    'quantity': quantity,
                    'results': results,
                    'progress_steps': results[0].get('progress_steps', []) if results else []
                }
            else:
                return self.create_purchase_order(user_input)
        
        elif 'UPDATE' in intent:
            return self.update_purchase_order(user_input)
            
        elif 'ANALYZE_QUESTION' in intent:
            # Intelligent question answering about PO data (includes transmission and error checks)
            return self._analyze_question_and_fetch_data(user_input)
            
        elif 'READ_PO' in intent:
            # Extract order number from user input
            order_number = self._extract_order_number(user_input)
            if order_number:
                # Check if user wants full details
                show_full = self._check_full_details_request(user_input)
                return self.read_purchase_order(order_number, show_full=show_full)
            else:
                return {'success': False, 'error': 'Please provide an order number to read PO details', 'operation': 'READ_PO'}
                
        elif 'KNOWLEDGE' in intent:
            # Query knowledge base for code definitions, status meanings, etc.
            return self._handle_knowledge_query(user_input)
            
        elif 'ANALYZE' in intent:
            return {'success': False, 'message': 'ANALYZE_DATA not yet implemented', 'operation': 'ANALYZE_DATA'}
        else:
            return {'success': False, 'message': 'Unable to determine intent', 'operation': 'UNKNOWN'}

    except Exception as e:
        return {'success': False, 'error': str(e), 'operation': 'CLASSIFICATION_ERROR'}


    def _handle_knowledge_query(self, user_query: str) -> Dict[str, Any]:
        """Handle knowledge base queries about POM codes, statuses, etc."""
        try:
            print(f"[_handle_knowledge_query] Processing query: {user_query}")

            # Query the RAG corpus or local knowledge base
            knowledge = self._query_rag_corpus(user_query, similarity_top_k=3)

            if knowledge and len(knowledge.strip()) > 5:
                # Use the LLM to generate a concise answer from the knowledge
                answer = self._answer_from_knowledge(user_query, knowledge)
                return {
                    'success': True,
                    'message': answer,
                    'operation': 'KNOWLEDGE_QUERY'
                }
            else:
                return {
                    'success': False,
                    'message': 'I could not find information about that in the knowledge base.',
                    'operation': 'KNOWLEDGE_QUERY'
                }
        except Exception as e:
            print(f"[_handle_knowledge_query] Error: {e}")
            return {
                'success': False,
                'error': f"Error querying knowledge base: {str(e)}",
                'operation': 'KNOWLEDGE_QUERY'
            }

    def verify_setup(self) -> Dict[str, bool]:
        """Verify that all required resources are available"""
        return {
            'config': self.config_path.exists(),
            'templates_dir': self.template_path.exists(),
            'sample_input_output_dir': self.sample_input_output_path.exists(),
            'sample_code_dir': self.sample_code_path.exists(),
            'prompts_dir': self.prompt_path.exists(),
            'create_po_input_template': (self.template_path / "create_po_api_input_template.json").exists(),
            'create_po_output_template': (self.template_path / "create_po_api_output_template.json").exists(),
            'create_po_input_sample': (self.sample_input_output_path / "create_po_api_input_sample.json").exists(),
            'create_po_output_sample': (self.sample_input_output_path / "create_po_api_output_sample.json").exists(),
            'update_po_input_template': (self.template_path / "update_po_api_input_template.json").exists(),
            'update_po_output_template': (self.template_path / "update_po_api_output_template.json").exists(),
            'update_po_input_sample': (self.sample_input_output_path / "update_po_api_input_sample.json").exists(),
            'update_po_output_sample': (self.sample_input_output_path / "update_po_api_output_sample.json").exists(),
            'update_po_sample_code': (self.sample_code_path / "sample_po_update_code.md").exists(),
            'create_po_sample_code': (self.sample_code_path / "sample_po_create_code.md").exists(),
            'update_po_sample_code_json': (self.sample_code_path / "sample_po_update_code.json").exists(),
        }
        
    
    def query(self, *, input: Optional[str] = None, prompt: Optional[str] = None, **kwargs):
        """
        Query method for Agent Engine compatibility.
        Agent Engine calls this method when deployed to cloud.
        Accepts both 'input' and 'prompt' parameters for flexibility.

        Args:
            input: User's natural language request (Agent Engine uses this)
            prompt: Alternative parameter name for user request
            **kwargs: Additional parameters

        Returns:
            Dictionary or string response (Agent Engine compatible)
        """
        try:
            # Agent Engine passes 'input', local testing uses 'prompt'
            user_input = input or prompt or ""
            print(f"[POMAgent.query] Received input: {user_input[:100]}...")
            print(f"[POMAgent.query] kwargs: {kwargs}")
            print(f"[POMAgent.query] project: {self.project_id}")

            if not user_input:
                return {"response": "Please provide a question or request.", "success": False}

            result = self.generate(user_input, **kwargs)
            print(f"[POMAgent.query] Generated response: {result[:100] if isinstance(result, str) else str(result)[:100]}...")

            # Return in format compatible with Agent Engine
            if isinstance(result, str):
                return {"response": result, "success": True}
            return result

        except Exception as e:
            error_msg = f"Error processing query: {str(e)}"
            print(f"[POMAgent.query] ERROR: {error_msg}")
            import traceback
            traceback.print_exc()
            return {"response": f"I apologize, but I encountered an error: {error_msg}\nPlease try again or rephrase your request.", "success": False, "error": str(e)}

    def set_up(self, **kwargs):
        """
        Setup method that Agent Engine may call during initialization.
        This is a no-op since initialization happens in __init__.
        """
        print(f"[POMAgent.set_up] Called with kwargs: {kwargs}")
        # Return immediately to avoid timeout - agent is already initialized
        return {"status": "ready"}

    async def query_async(self, prompt: str, **kwargs) -> str:
        """
        Async query method for Agent Engine compatibility.
        Some Agent Engine deployments may require async methods.
        Args: 
            prompt: User's natural language request
            **kwargs: Additional parameters

        Returns:
            String response with the result
        """
        return self.generate(prompt, **kwargs)

    def _execute_tasklist(self, prompt: str) -> str:
        """
        Execute a tasklist in JSON format with context preservation.

        Format:
        {
            "test_steps":{
                "task_1":"Create a new PO for Import Transload at location 5098",
                "task_2":"Update totalShippedQuantity to 20 for SKU 1001397562 on that new PO",
                "task_3":"provide a summary of adjusted, shipped, and received quantities for all SKUs on that PO.",
                "task_4":"provide summary of these actions"
            }
        }

        Args:
            prompt: The tasklist request containing JSON

        Returns:
            Combined results from all tasks
        """
        import json
        import re

        try:
            print(f"[_execute_tasklist] Parsing tasklist request")

            # Extract JSON from the prompt
            json_match = re.search(r'\{[^{}]*"test_steps"[^{}]*\{([^}]+)\}[^}]*\}', prompt, re.DOTALL)
            if not json_match:
                return f"❌ Could not find valid tasklist JSON in request. Please use format:\n\n  \"test_steps\":{\n      \"task_1\":\"your task\",\n      \"task_2\":\"your task\"\n  }"

            # Parse the JSON
            tasklist_json = json.loads(json_match.group(0))
            tasks = tasklist_json.get('test_steps', {})

            if not tasks:
                return "❌ No tasks found in test_steps"

            # Sort tasks by key (task_1, task_2, etc.)
            sorted_task_keys = sorted(tasks.keys(), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)

            print(f"[_execute_tasklist] Found {len(sorted_task_keys)} tasks to execute")

            # Context to carry forward between tasks
            context = {
                'order_number': None,
                'po_request_id': None,
                'results': []
            }

        # Execute each task sequentially
        for task_key in sorted_task_keys:
            task_instruction = tasks[task_key]
            print(f"[_execute_tasklist] Executing {task_key}: {task_instruction[:50]}...")

            # Replace references to "that PO", "that po", "that order", etc. with actual order number
            enhanced_instruction = self._enhance_instruction_with_context(task_instruction, context)
            print(f"[_execute_tasklist] Enhanced instruction: {enhanced_instruction}")

            # Execute the task
            result = self.process_natural_language_request(enhanced_instruction)

            # Update context with order number and po_request_id if this was a CREATE_PO
            if result.get('operation') == 'CREATE_PO' and result.get('success'):
                if result.get('order_number'):
                    context['order_number'] = result['order_number']
                    print(f"[_execute_tasklist] Captured order_number: {context['order_number']}")
                if result.get('po_request_id'):
                    context['po_request_id'] = result['po_request_id']
                    print(f"[_execute_tasklist] Captured po_request_id: {context['po_request_id']}")

            # Format and store the result
            formatted_result = self._format_step_response(result)
            context['results'].append({
                'task': task_key,
                'instruction': task_instruction,
                'result': formatted_result,
                'success': result.get('success', False)
            })

        # Build final response
        response = "## Tasklist Execution Results\n\n"

        for item in context['results']:
            response += f"### {item['task'].replace('_', ' ').title()}\n"
            response += f"**Instruction:** {item['instruction']}\n\n"
            response += f"{item['result']}\n\n"
            response += "---\n\n"

        # Add summary
        response += "## Summary\n\n"
        response += f"✅ **Completed {len(context['results'])} tasks**\n\n"

        if context['order_number']:
            response += f"**Order Number:** {context['order_number']}\n"
        if context['po_request_id']:
            response += f"**PO Request ID:** {context['po_request_id']}\n"

        successful_tasks = sum(1 for r in context['results'] if r['success'])
        failed_tasks = len(context['results']) - successful_tasks

        response += f"\n\nSuccess:** {successful_tasks} | **Failed:** {failed_tasks}\n"

        return response

    except json.JSONDecodeError as e:
        print(f"[_execute_tasklist] JSON parse error: {e}")
        return f"❌ Invalid JSON format: {str(e)}\n\nPlease use valid JSON format for test_steps"
    except Exception as e:
        print(f"[_execute_tasklist] Error executing tasklist: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Error executing tasklist: {str(e)}"

def _enhance_instruction_with_context(self, instruction: str, context: Dict[str, Any]) -> str:
    """Replace context placeholders in instruction with actual values and auto-append order number when needed"""
    enhanced = instruction

    # Replace "that PO", "that po", "that order", etc. with actual order number
    if context.get('order_number'):
        # Convert order_number to string for regex replacement
        order_number_str = str(context['order_number'])

        import re

        # Comprehensive patterns to match various phrasings
        # Order matters - more specific patterns first
        # Use "order X" format since that's what the agent recognizes best
        replacements = [
            # Patterns with "new" and additional context
            (r'\bfor\s+the\s+new\s+po\s+from\s+task\d+\b', f"for order {order_number_str}"),
            (r'\bfor\s+that\s+new\s+po\s+from\s+task\d+\b', f"for order {order_number_str}"),
            (r'\bon\s+the\s+new\s+po\s+from\s+task\d+\b', f"on order {order_number_str}"),
            (r'\bon\s+that\s+new\s+po\s+from\s+task\d+\b', f"on order {order_number_str}"),

            # Patterns with "new"
            (r'\bfor\s+the\s+new\s+po\b', f"for order {order_number_str}"),
            (r'\bfor\s+that\s+new\s+po\b', f"for order {order_number_str}"),
            (r'\bon\s+the\s+new\s+po\b', f"on order {order_number_str}"),
            (r'\bon\s+that\s+new\s+po\b', f"on order {order_number_str}"),
            (r'\bof\s+the\s+new\s+po\b', f"of order {order_number_str}"),
            (r'\bof\s+that\s+new\s+po\b', f"of order {order_number_str}"),
            (r'\bthat\s+new\s+po\b', f"order {order_number_str}"),
            (r'\bthe\s+new\s+po\b', f"order {order_number_str}"),
            (r'\bthat\s+new\s+purchase\s+order\b', f"order {order_number_str}"),

            # Patterns without "new"
            (r'\bfor\s+that\s+po\b', f"for order {order_number_str}"),
            (r'\bfor\s+the\s+po\b', f"for order {order_number_str}"),
            (r'\bon\s+that\s+po\b', f"on order {order_number_str}"),
            (r'\bon\s+the\s+po\b', f"on order {order_number_str}"),
            (r'\bof\s+that\s+po\b', f"of order {order_number_str}"),
            (r'\bof\s+the\s+po\b', f"of order {order_number_str}"),
            (r'\bthat\s+po\b', f"order {order_number_str}"),
            (r'\bthe\s+po\b', f"order {order_number_str}"),
            (r'\bthat\s+order\b', f"order {order_number_str}"),
            (r'\bthe\s+order\b', f"order {order_number_str}"),
            (r'\bthat\s+purchase\s+order\b', f"order {order_number_str}"),
        ]

        for pattern, replacement in replacements:
            enhanced = re.sub(pattern, replacement, enhanced, flags=re.IGNORECASE)

        # Check if the instruction looks like an operation that needs order number
        # This handles cases where user mentions operations without specifying which PO
        operation_keywords = [
            'update', 'change', 'modify', 'set',         # Update operations
            'verify', 'check', 'show', 'display',        # Read/verify operations
            'get', 'read', 'retrieve', 'find',           # Read operations
            'cancel', 'close',                            # Status change operations
            'transmission', 'transmit', 'transmitted',    # Transmission check operations
            'status', 'error', 'errors'                  # Status/error check operations
        ]

        # Check if any operation keyword is present in the instruction
        has_operation_keyword = any(keyword in enhanced.lower() for keyword in operation_keywords)

        # Check if order number is already mentioned (only check for explicit "order X" or "PO X" format)
        # Don't match bare numbers since those could be SKUs, quantities, etc.
        has_order_reference = (
            re.search(r'\border\s+\d+\b', enhanced, re.IGNORECASE) or
            re.search(r'\bpo\s+\d+\b', enhanced, re.IGNORECASE) or
            re.search(r'\bpurchase\s+order\s+\d+\b', enhanced, re.IGNORECASE)
        )

        # If it's an update/read operation without order reference, append it
        if has_operation_keyword and not has_order_reference:
            enhanced = f"{enhanced} for order {order_number_str}"
            print(f"[_enhance_instruction_with_context] Auto-appended order number to instruction")

    return enhanced

    def _format_step_response(self, result: Dict[str, Any]) -> str:
        """Format a single step result for sequential execution output"""
        if not result.get('success'):
            error_msg = result.get('error', result.get('message', 'Unknown error'))
            operation = result.get('operation', 'UNKNOWN')
            return f"❌ **Failed:** {operation}\n**Error:** {error_msg}"

        operation = result.get('operation', 'UNKNOWN')

        # Format based on operation type
        if operation == 'CREATE_PO':
            return f"✅ **Created PO**\n\n* **Order Number:** {result.get('order_number', 'N/A')}\n* **PO Request ID:** {result.get('po_request_id', 'N/A')}"

        elif operation == 'UPDATE_PO':
            return f"✅ **Updated PO**\n\n* **Order Number:** {result.get('order_number', 'N/A')}"

        elif operation == 'READ_PO':
            return f"✅ **Retrieved PO Details**\n\n* **Order Number:** {result.get('order_number', 'N/A')}"

        elif operation == 'READ_PO_TRANSMISSION':
            transmission_details = result.get('transmission_details', {})
            total = transmission_details.get('total_records', 0)
            return f"✅ **Retrieved Transmission Status**\n\n* **Total Records:** {total}"

        elif operation == 'READ_PO_ERRORS':
            error_details = result.get('error_details', {})
            total = error_details.get('total_records', 0)
            return f"✅ **Retrieved Error Details**\n\n* **Total Errors:** {total}"

        elif operation == 'ANALYZE_QUESTION':
            answer = result.get('answer', 'No answer provided')
            return f"✅ **Analysis Complete:**\n\n{answer}"

        else:
            return f"✅ **{operation} Completed**"

    def generate(self, prompt, **kwargs) -> str:
        """
        Main entry point for ADK - processes user prompts and returns responses.
        This method is required by BaseAgent for ADK compatibility.
        
        Args:
            prompt: User's natural language request (can be string or InvocationContext)
            **kwargs: Additional parameters
        Returns:
            String response with the result.
        """

        try:
            # Handle InvocationContext object from Agent Engine
            from google.adk.runners import InvocationContext
            if isinstance(prompt, InvocationContext):
                # Try to extract the actual user input from InvocationContext
                # The user's message is in user_content attribute, which contains parts
                if hasattr(prompt, 'user_content') and prompt.user_content:
                    user_content = prompt.user_content
                    # user_content has 'parts' attribute with text
                    if hasattr(user_content, 'parts') and user_content.parts:
                        # Get text from the first part
                        if len(user_content.parts) > 0 and hasattr(user_content.parts[0], 'text'):
                            actual_prompt = user_content.parts[0].text
                            print(f"[POMAgent.generate] Extracted text from prompt.user_content.parts[0].text")
                        else:
                        actual_prompt = str(user_content)
                        print(f"[POMAgent.generate] Extracted from str(prompt.user_content)")    
                    else:
                        actual_prompt = str(user_content)
                        print(f"[POMAgent.generate] Extracted from str(prompt.user_content)")
                elif hasattr(prompt, 'message') and prompt.message:
                    actual_prompt = prompt.message
                    print(f"[POMAgent.generate] Extracted from prompt.message")
                elif hasattr(prompt, 'input') and isinstance(prompt.input, str):
                    actual_prompt = prompt.input
                    print(f"[POMAgent.generate] Extracted from prompt.input")
                else:
                    # Fallback to string conversion
                    actual_prompt = str(prompt)
                    print(f"[POMAgent.generate] Fallback to str(prompt)")

            print(f"[POMAgent.generate] Extracted prompt (first 200 chars): {actual_prompt[:200] if isinstance(actual_prompt, str) else actual_prompt}")

            # Check if this is a tasklist request (new JSON format)
            if isinstance(actual_prompt, str) and "test_steps" in actual_prompt:
                print("[POMAgent.generate] ✓ DETECTED TASKLIST REQUEST")
                return self._execute_tasklist(actual_prompt)

            # Normal single-action processing
            result = self.process_natural_language_request(actual_prompt)
            print(f"[POMAgent.generate] Result: {result.get('operation', 'UNKNOWN')}, success: {result.get('success')}")

            if result.get('success'):
                operation = result.get('operation', 'UNKNOWN')

                # Handle greetings and conversations
                if operation in ['GREETING', 'HELP', 'CONVERSATION']:
                    response = result.get('message', 'Hello!')
                    print(f"[POMAgent.generate] Returning greeting: {response}")
                    return response

                # Handle PO operations with simplified output
                if operation == 'CREATE_PO':
                    progress = '\n'.join(result.get('progress_steps', []))
                    order_num = result.get('order_number', 'N/A')
                    status_code = result.get('status_code')

                    response_msg = f"""✅ **Purchase Order Created Successfully!
    **Progress**
    {progress}
    **PO Request ID:** {result.get('po_request_id')}
    **Order Number:** {order_num}
    **Status Code:** {status_code}
    """
                    # Add response details
                    response_data=result.get('response',{})
                    if response_data and isinstance(response_data,dict):
                         if 'message' in response_data:
                             response_msg += f"\n**Message:** {response_data['message']}"
                    return response_msg

                elif operation = 'CREATE_MULTIPLE_PO':
                     quantity = result-get(quantity',0)
                     results = result. get('results', [1)
                     progress = "\n'.join(result. get('progress_steps', []))
                     response = f"""✅{quantity} Purchase Orders Created Successfully!
*Progress:* 
{progress}

**Created POs:**"""
                    for idx, po_result in enumerate(results, 1):
                        response += f"""
                    {idx}. *PO Request ID:* {po_result.get('po_request_id')}
                    **Order Number:** {po_result.get ('order_number', 'N/A')}
                    **Status Code:** {po_result.get('status_code')}"""
                    return response

                elif operation = 'UPDATE_PO':
                     progress = '\n'.join(result. get('progress_steps', (1))
                     return f"""✅Purchase Order Updated Successfully!
*Progress：
{progress}

**Order Number:** {result.get ('order_number')}
**Status Code:** {result.get('status_code')}."""

                elif operation == 'READ_PO':
                    order_number = result.get('order_number')
                    progress = '\n'.join(result.get('progress_steps', []))
                    po_details = result.get('po_details', {})
                    show_full = result.get('show_full', False)

                    # Use intelligent formatting
                    if show_full:
                        # Show complete raw data
                        formatted_data = json.dumps(po_details, indent=2)
                    else:
                        # Show brief summary
                        formatted_data = self._format_po_brief(po_details)

                    return f"""✅ **Purchase Order Details Retrieved!**

    **Progress:**
    {progress}
    
    **Order Number:** {order_number}
    **Status Code:** {result.get('status_code')}



    {formatted_data}"""

                elif operation == 'READ_PO_TRANSMISSION':
                    progress = '\n'.join(result.get('progress_steps', []))
                    transmission_details = result.get('transmission_details', {})

                    # Use intelligent formatting with code translation
                    formatted_summary = self._format_transmission_summary(transmission_details)

                    return f"""✅ **PO Transmission Status Retrieved!**

    **Order Number:** {result.get('order_number')}
    **Status Code:** {result.get('status_code')}

    **Progress:**
    {progress}

    {formatted_summary}"""

                elif operation == 'READ_PO_ERRORS':
                    progress = '\n'.join(result.get('progress_steps', []))
                    error_details = result.get('error_details', {})

                    # Use intelligent formatting with error analysis
                    formatted_summary = self._format_error_summary(error_details)

                    return f"""✅ **PO Error Details Retrieved!**

    **Order Number:** {result.get('order_number')}
    **Status Code:** {result.get('status_code')}

    **Progress:**
    {progress}

    {formatted_summary}"""

                elif operation == 'ANALYZE_QUESTION':
                    # Intelligent question answering
                    answer = result.get('answer', '')
                    order_number = result.get('order_number', 'N/A')
                    api_called = result.get('api_called', 'N/A')

                    return f"""✅ **Analysis Complete!**

    **Order Number:** {order_number}
    **Data Source:** {api_called}

    {answer}

    *This answer was generated by analyzing the purchase order data and enriched with knowledge base translations for codes and statuses.*"""

                elif operation == 'KNOWLEDGE_QUERY':
                    # Return knowledge base query results directly
                    message = result.get('message', '')
                    return message if message else "No information found in knowledge base."

                else:
                    return f"✅ Operation completed: {operation}"

            else:
                # Enhanced error response with details
                error_msg = result.get('error', result.get('message', 'Unknown error'))
                operation = result.get('operation', 'UNKNOWN')
                error_response = f"❌ **Operation Failed: {operation}**\n\n**Error:** {error_msg}"

                # Add detailed error information for CREATE_PO failures
                if operation == 'CREATE_PO':
                    po_request_id = result.get('po_request_id', 'N/A')
                    status_code = result.get('status_code', 'N/A')
                    error_response += f"\n\n**PO Request ID:** {po_request_id}\n**Status Code:** {status_code}"

                    # Include API response details if available
                    response_data = result.get('response', {})
                    if response_data and isinstance(response_data, dict):
                        if 'error' in response_data:
                            error_response += f"\n\n**API Error Details:** {response_data['error']}"
                        elif 'message' in response_data:
                            error_response += f"\n\n**API Message:** {response_data['message']}"
                        elif 'errors' in response_data:
                            error_response += f"\n\n**Validation Errors:**"
                            for err in response_data['errors']:
                                if isinstance(err, dict):
                                    field = err.get('field', 'unknown')
                                    msg = err.get('message', str(err))
                                    error_response += f"\n* **{field}**: {msg}"
                                else:
                                    error_response += f"\n* {err}"

                            else:
                                # Show full response if structure is unknown
                                error_response += f"\n\n**API Response:**\n```json\n{json.dumps(response_data, indent=2)}\n```"
                        else:
                             error_response += f"\n\n**API Response:**{response_data}"
                    # Add progress steps if available
                    progress_steps = result.get('progress_steps', [])
                    if progress_steps:
                        error_response += f"\n\n**Progress:**\n" + '\n'.join(progress_steps)
                
                # Add detailed error information for READ_PO_ERRORS failures
                elif operation == 'READ_PO_ERRORS':
                    order_number = result.get('order_number', 'N/A')
                    status_code = result.get('status_code', 'N/A')
                    error_response += f"\n\n**Order Number:** {order_number}\n**Status Code:** {status_code}"

                    # Show detailed error if available
                    error_details = result.get('error_details', {})
                    if error_details:
                        if isinstance(error_details, dict):
                            if 'message' in error_details:
                                error_response += f"\n\n**Details:** {error_details['message']}"
                            if 'raw_response' in error_details:
                                error_response += f"\n\n**API Response:**\n```json\n{json.dumps(error_details['raw_response'], indent=2)}\n```"
                        else:
                            error_response += f"\n\n**Details:** {error_details}"
                            
                    # Add progress steps if available
                    progress_steps = result.get('progress_steps', [])
                    if progress_steps:
                        error_response += f"\n\n**Progress:**\n" + '\n'.join(progress_steps)

                # Generic handling for other operations
                else:
                    order_number = result.get('order_number', None)
                    status_code = result.get('status_code', None)
                    if order_number:
                        error_response += f"\n\n**Order Number:** {order_number}"
                    if status_code:
                        error_response += f"\n\n**Status Code:** {status_code}"

                    progress_steps = result.get('progress_steps', [])
                    if progress_steps:
                        error_response += f"\n\n**Progress:**\n" + '\n'.join(progress_steps)

                return error_response

        except Exception as e:
            print(f"[POMAgent.generate] Exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"❌ Error processing request: {str(e)}"

        async def _run_async_impl(self, request, **kwargs):
            """
            Async implementation required by BaseAgent.
            Must be an async generator that yields events.
            Args:
                request: user natural language qs
            # Yield objects with proper structure including invocation_id
            # kwargs: Additional parameters including invocation_id
            """

            
            from google.adk.events import Event
            from google.genai.types import Content, Part
            from google.adk.runners import InvocationContext
            
            # Extract invocation_id if available"""

            invocation_id = None
            if isinstance(request, InvocationContext):
                invocation_id = getattr(request, 'invocation_id', None)
                print(f"[POMAgent._run_async_impl] InvocationContext invocation_id: {invocation_id}")

            # Also check kwargs for invocation_id
            if not invocation_id and 'invocation_id' in kwargs:
                invocation_id = kwargs['invocation_id']
                print(f"[POMAgent._run_async_impl] kwargs invocation_id: {invocation_id}")

            # Generate the response synchronously
            response = self.generate(request, **kwargs)

            # Create properly structured Event with Content and Invocation_id
            content = Content(parts=[Part(text=response)], role='model')
            event_kwargs = {'content': content, 'author': 'agent', 'partial': False}

            # Add invocation_id if available
            if invocation_id:
                event_kwargs['invocation_id'] = invocation_id
                print(f"[POMAgent._run_async_impl] Created event with invocation_id: {invocation_id}")

            event = Event(**event_kwargs)
            yield event

# Alias for backward compatibility
POMSystemManagerAgent = POMAgent

# Create root_agent instance for ADK deployment
# Using the correct Google Cloud project ID
root_agent = POMAgent(project_id="your-project-id")

if __name__ == "__main__":
    # Example usage
    agent = POMAgent(project_id="your-project-id")
    # Verify setup
    status = agent.verify_setup()
    print("Setup Status:")
    for key, value in status.items():
        symbol = "✓" if value else "x"
        print(f"  {symbol} {key}")

    # Example request
    result = agent.process_natural_language_request(
        "Create a purchase order for vendor 17404"
    )
    print(f"\nResult: {json.dumps(result, indent=2)}")

                

            