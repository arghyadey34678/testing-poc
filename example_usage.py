


"""
Example usage: Unified POM Agent
================================
"""

import os
import json
from pom_testing_agent import POMAgent

def example_1_simple_creation():
    """Example 1: Simple PO Creation"""
    print("=" * 60)
    print("Example 1: Simple PO Creation")
    print("=" * 60)

    agent = POMAgent(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    )

    # Verify setup
    print("\n📋 Verifying setup...")
    status = agent.verify_setup()
    for resource, available in status.items():
        symbol = "✅" if available else "❌"
        print(f"  {symbol} {resource}")

    # Create PO
    print("\n📝 Creating purchase order...")
    result = agent.create_purchase_order(
        "Create a purchase order for vendor 17404"
    )

    if result['success']:
        print(f"\n✅ Success!")
        print(f"   Order Number: {result.get('order_number')}")
        print(f"   PO Request ID: {result['po_request_id']}")
    else:
        print(f"\n❌ Failed: {result.get('error')}")

    return result

def example_2_natural_language():
    """Example 2: Natural Language Processing"""
    print("\n" + "=" * 60)
    print("Example 2: Natural Language Processing")
    print("=" * 60)

    agent = POMAgent(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    )

    # Process natural language request
    print("\n💬 Processing natural language request...")
    result = agent.process_natural_language_request(
        "I need to create a new purchase order for 100 units of item SKU-12345 from vendor V123"
    )

    print(f"\n🔍 Operation: {result['operation']}")
    print(f"   Success: {result['success']}")

    if result['success'] and result.get('order_number'):
        print(f"   Order Number: {result['order_number']}")
        print(f"   PO Request ID: {result['po_request_id']}")

    return result

def example_3_detailed_result():
    """Example 3: Detailed Result Inspection"""
    print("\n" + "=" * 60)
    print("Example 3: Detailed Result Inspection")
    print("=" * 60)

    agent = POMAgent(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    )

    result = agent.create_purchase_order(
        "Create PO for vendor 17404 with item 12345, quantity 50"
    )

    print("\n📊 Full Result:")
    print(json.dumps(result, indent=2, default=str))

    return result

def example_4_error_handling():
    """Example 4: Error Handling"""
    print("\n" + "=" * 60)
    print("Example 4: Error Handling")
    print("=" * 60)

    agent = POMAgent(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    )

    # Try with invalid project (will fail gracefully)
    print("\n🧪 Testing error handling...")
    result = agent.process_natural_language_request(
        "Create a purchase order"
    )

    if not result['success']:
        print(f"✔️ Error handled gracefully")
        print(f"   Error: {result.get('error', 'Unknown error')}")
    else:
        print(f"✔️ Operation succeeded")
        print(f"   Order: {result.get('order_number')}")

    return result

def example_5_config_inspection():
    """Example 5: Inspect Configuration"""
    print("\n" + "=" * 60)
    print("Example 5: Configuration Inspection")
    print("=" * 60)

    agent = POMAgent(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT', 'your-project-id')
    )

    print("\n🔧 API Configuration:")
    if 'create_po_api' in agent.api_config:
        config = agent.api_config['create_po_api']
        print(f"   API Name: {config.get('api_name')}")
        print(f"   Secured: {config.get('is_secured')}")
        print(f"   Method: {config.get('method_type')}")
        print(f"   Endpoint: {config.get('end_point')}")
    else:
        print("   ⚠️  No API configuration loaded")

    print("\n📁 Available Templates:")
    for name in agent.templates.keys():
        print(f"   ✓ {name}")

    print("\n📋 Available Samples:")
    for name in agent.samples.keys():
        print(f"   ✓ {name}")

    return agent

if __name__ == "__main__":
    print("\n" + "🚀" + "=" * 56 + "🚀")
    print("    Unified POM Agent - Example Usage")
    print("🚀" + "=" * 56 + "🚀\n")

    # Set up environment
    if not os.getenv('GOOGLE_CLOUD_PROJECT'):
        print("⚠️  Warning: GOOGLE_CLOUD_PROJECT not set")
        print("   Using placeholder project ID for demo\n")

    try:
        # Run examples
        example_1_simple_creation()
        example_2_natural_language()
        example_3_detailed_result()
        example_4_error_handling()
        example_5_config_inspection()

        print("\n" + "=" * 60)
        print("✅ All examples completed!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error running examples: {e}\n")
        import traceback
        traceback.print_exc()