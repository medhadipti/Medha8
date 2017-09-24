import ast
import itertools
from collections import namedtuple

from .ast_helper import Arguments, get_call_names_as_string
from .label_visitor import LabelVisitor
from .right_hand_side_visitor import RHSVisitor
from .vars_visitor import VarsVisitor
from pyt.utils.log import enable_logger, logger
enable_logger(to_file='./pyt.log')


ControlFlowNode = namedtuple('ControlFlowNode',
                             'test last_nodes break_statements')

ConnectStatements = namedtuple('ConnectStatements',
                               'first_statement' +
                               ' last_statements' +
                               ' break_statements')
CALL_IDENTIFIER = '¤'


class IgnoredNode():
    """Ignored Node sent from an ast node that should not return anything."""


class Node():
    """A Control Flow Graph node that contains a list of
    ingoing and outgoing nodes and a list of its variables."""

    def __init__(self, label, ast_node, *, line_number, path):
        """Create a Node that can be used in a CFG.

        Args:
            label (str): The label of the node, describing its expression.
            line_number(Optional[int]): The line of the expression of the Node.
        """
        self.label = label
        self.ast_node = ast_node
        self.line_number = line_number
        self.path = path
        self.ingoing = list()
        self.outgoing = list()

    def connect(self, successor):
        """Connect this node to its successor node by
        setting its outgoing and the successors ingoing."""
        if isinstance(self, ConnectToExitNode) and\
           not isinstance(successor, EntryOrExitNode):
            return

        # Debug connects!
        # first = 'Exit does_this_kill_us'
        # second = 'call_5'
        # if first in self.label or first in successor.label:
        #     logger.debug("self.label is %s", self.label)
        #     logger.debug("successor.label is %s", successor.label)
        #     # raise
        #     if second in successor.label or second in self.label:
        #         logger.debug("I am being connected to %s", successor)
        #         raise

        self.outgoing.append(successor)
        successor.ingoing.append(self)

    def connect_predecessors(self, predecessors):
        """Connect all nodes in predecessors to this node."""
        for n in predecessors:
            self.ingoing.append(n)
            n.outgoing.append(self)

    def __str__(self):
        """Print the label of the node."""
        return ''.join((' Label: ', self.label))


    def __repr__(self):
        """Print a representation of the node."""
        label = ' '.join(('Label: ', self.label))
        line_number = 'Line number: ' + str(self.line_number)
        outgoing = ''
        ingoing = ''
        if self.ingoing:
            ingoing = ' '.join(('ingoing:\t', str([x.label for x in self.ingoing])))
        else:
            ingoing = ' '.join(('ingoing:\t', '[]'))

        if self.outgoing:
            outgoing = ' '.join(('outgoing:\t', str([x.label for x in self.outgoing])))
        else:
            outgoing = ' '.join(('outgoing:\t', '[]'))

        return '\n' + '\n'.join((label, line_number, ingoing, outgoing))


class ConnectToExitNode():
    pass


class FunctionNode(Node):
    """CFG Node that represents a function definition.

    Used as a dummy for creating a list of function definitions.
    """

    def __init__(self, ast_node):
        """Create a function node.

        This node is a dummy node representing a function definition.
        """
        super().__init__(self.__class__.__name__, ast_node)


class RaiseNode(Node, ConnectToExitNode):
    """CFG Node that represents a Raise statement."""

    def __init__(self, label, ast_node, *, line_number, path):
        """Create a Raise node."""
        super().__init__(label, ast_node, line_number=line_number, path=path)


class BreakNode(Node):
    """CFG Node that represents a Break node."""

    def __init__(self, ast_node, *, line_number, path):
        super().__init__(self.__class__.__name__, ast_node, line_number=line_number, path=path)


class EntryOrExitNode(Node):
    """CFG Node that represents an Exit or an Entry node."""

    def __init__(self, label):
        super().__init__(label, None, line_number=None, path=None)


class AssignmentNode(Node):
    """CFG Node that represents an assignment."""

    def __init__(self, label, left_hand_side, ast_node, right_hand_side_variables, vv_result, *, line_number, path):
        """Create an Assignment node.

        Args:
            label (str): The label of the node, describing the expression it represents.
            left_hand_side(str): The variable on the left hand side of the assignment. Used for analysis.
            right_hand_side_variables(list[str]): A list of variables on the right hand side.
            vv_result(list[str]): Necessary to know `image_name = image_name.replace('..', '')` is a reassignment.
            line_number(Optional[int]): The line of the expression the Node represents.
        """
        super().__init__(label, ast_node, line_number=line_number, path=path)
        self.left_hand_side = left_hand_side
        self.right_hand_side_variables = right_hand_side_variables
        # Only set in assignment_call_node()
        self.vv_result = vv_result
        # Only set True in assignment_call_node()
        self.blackbox = False

    def __repr__(self):
        output_string = super().__repr__()
        output_string += '\n'
        return ''.join((output_string,
                        'left_hand_side:\t', str(self.left_hand_side), '\n',
                        'right_hand_side_variables:\t', str(self.right_hand_side_variables)))


class RestoreNode(AssignmentNode):
    """Node used for handling restore nodes returning from function calls."""

    def __init__(self, label, left_hand_side, right_hand_side_variables, *, line_number, path):
        """Create a Restore node.

        Args:
            label (str): The label of the node, describing the expression it represents.
            left_hand_side(str): The variable on the left hand side of the assignment. Used for analysis.
            right_hand_side_variables(list[str]): A list of variables on the right hand side.
            line_number(Optional[int]): The line of the expression the Node represents.
        """
        super().__init__(label, left_hand_side, None, right_hand_side_variables, None, line_number=line_number, path=path)


class BBnode(AssignmentNode):
    """Node used for handling restore nodes returning from function calls."""

    def __init__(self, label, left_hand_side, right_hand_side_variables, *, line_number, path):
        """Create a Restore node.

        Args:
            label(str): The label of the node, describing the expression it represents.
            left_hand_side(str): The variable on the left hand side of the assignment. Used for analysis.
            right_hand_side_variables(list[str]): A list of variables on the right hand side.
            line_number(Optional[int]): The line of the expression the Node represents.
            path?
        """
        super().__init__(label, left_hand_side, None, right_hand_side_variables, None, line_number=line_number, path=path)
        self.args = []


class ReturnNode(AssignmentNode, ConnectToExitNode):
    """CFG node that represents a return from a call."""

    def __init__(self, label, left_hand_side, right_hand_side_variables, ast_node, *, line_number, path):
        """Create a CallReturn node.

        Args:
            label (str): The label of the node, describing the expression it represents.
            restore_nodes(list[Node]): List of nodes that were restored in the function call.
            right_hand_side_variables(list[str]): A list of variables on the right hand side.
            line_number(Optional[int]): The line of the expression the Node represents.
            path?
        """
        super().__init__(label, left_hand_side, ast_node, right_hand_side_variables, None, line_number=line_number, path=path)


class Function():
    """Representation of a function definition in the program."""

    def __init__(self, nodes, args, decorator_list):
        """Create a Function representation.

        Args:
            nodes(list[Node]): The CFG of the Function.
            args(ast.args): The arguments from a function AST node.
            decorator_list(list[ast.decorator]): The list of decorators
            from a function AST node.
        """
        self.nodes = nodes
        self.arguments = Arguments(args)
        self.decorator_list = decorator_list

    def __repr__(self):
        output = ''
        for x, n in enumerate(self.nodes):
            output = ''.join((output, 'Node: ' + str(x) + ' ' + repr(n), '\n\n'))
        return output

    def __str__(self):
        output = ''
        for x, n in enumerate(self.nodes):
            output = ''.join((output, 'Node: ' + str(x) + ' ' + str(n), '\n\n'))
        return output


class CFG():
    def __init__(self, nodes, blackbox_assignments):
        self.nodes = nodes
        self.blackbox_assignments = blackbox_assignments

    def __repr__(self):
        output = ''
        for x, n in enumerate(self.nodes):
            output = ''.join((output, 'Node: ' + str(x) + ' ' + repr(n), '\n\n'))
        return output

    def __str__(self):
        output = ''
        for x, n in enumerate(self.nodes):
            output = ''.join((output, 'Node: ' + str(x) + ' ' + str(n), '\n\n'))
        return output


class Visitor(ast.NodeVisitor):

    def append_node(self, Node):
        """Append a node to the CFG and return it."""
        self.nodes.append(Node)
        return Node

    def get_first_statement(self, node_or_tuple):
        """Find the first statement of the provided object.

        Returns:
            The first element in the tuple if it is a tuple.
            The node if it is a node.
        """
        if isinstance(node_or_tuple, tuple):
            return node_or_tuple[0]
        else:
            return node_or_tuple

    def node_to_connect(self, node):
        """Determine if node should be in the final CFG."""
        if isinstance(node, (FunctionNode, IgnoredNode)):
            return False
        else:
            return True

    def connect_control_flow_node(self, control_flow_node, next_node):
        """Connect a ControlFlowNode properly to the next_node."""
        for last in control_flow_node[1]:  # list of last nodes in ifs and elifs
            if isinstance(next_node, ControlFlowNode):
                last.connect(next_node.test)  # connect to next if test case
            else:
                last.connect(next_node)

    def connect_nodes(self, nodes):
        """Connect the nodes in a list linearly."""
        for n, next_node in zip(nodes, nodes[1:]):
            logger.debug("DEATH")
            logger.debug("n is %s", n)
            logger.debug("next_node is %s", next_node)
            if isinstance(n, ControlFlowNode):  # case for if
                self.connect_control_flow_node(n, next_node)
            elif isinstance(next_node, ControlFlowNode):  # case for if
                n.connect(next_node[0])
            elif isinstance(next_node, RestoreNode):
                continue
            elif CALL_IDENTIFIER in next_node.label:
                continue
            else:
                n.connect(next_node)

    def get_last_statements(self, cfg_statements):
        """Retrieve the last statements from a cfg_statements list."""
        if isinstance(cfg_statements[-1], ControlFlowNode):
            return cfg_statements[-1].last_nodes
        else:
            return [cfg_statements[-1]]

    def stmt_star_handler(self, stmts, prev_node_to_avoid=None):
        """Handle stmt* expressions in an AST node.

        Links all statements together in a list of statements, accounting for statements with multiple last nodes.
        """
        break_nodes = list()
        cfg_statements = list()

        if prev_node_to_avoid:
            self.prev_nodes_to_avoid.append(prev_node_to_avoid)

        first_node = None
        logger.debug("\n\n\n***********in stmt_star_handler self.nodes[-1] is %s***************\n\n\n\n\n", self.nodes[-1])
        node_not_to_step_passed = self.nodes[-1]

        for stmt in stmts:
            logger.debug("[kaytranada]stmt is %s", stmt)

            node = self.visit(stmt)
            if isinstance(stmt, ast.While) or isinstance(stmt, ast.For):
                self.last_was_loop_stack.append(True)
            else:
                self.last_was_loop_stack.append(False)

            logger.debug("[kaytranada]node is %s", node)
            logger.debug("[kaytranada]type(node) is %s", type(node))

            if isinstance(node, ControlFlowNode):
                break_nodes.extend(node.break_statements)
            elif isinstance(node, BreakNode):
                break_nodes.append(node)

            logger.debug("BEFORE so first_node is %s", first_node)

            if node and not first_node: # (Make sure first_node isn't already set.)
                # first_node is always a "node_to_connect", because it won't have ingoing otherwise
                # If we have e.g.
                #   import os # An ignored node
                #   value = None
                # first_node will be `value = None`
                if hasattr(node, 'ingoing'):
                    ingoing = None
                    current_node = node
                    while current_node.ingoing:
                        # e.g. We don't want to step passed the Except of an Except BB
                        if current_node.ingoing[0] == node_not_to_step_passed:
                            break
                        logger.debug("CURRENT_NODE is %s", current_node)
                        logger.debug("current_node.ingoing is %s", current_node.ingoing)
                        logger.debug("current_node.ingoing[0] is %s", current_node.ingoing[0])
                        logger.debug("current_node.ingoing[0].ingoing is %s", current_node.ingoing[0].ingoing)

                        ingoing = current_node.ingoing
                        current_node = current_node.ingoing[0]
                    if ingoing:
                        # Only set it once
                        first_node = ingoing[0]
            logger.debug("here in my, node is %s", node)
            if self.node_to_connect(node) and node:
                if not first_node:
                    if isinstance(node, ControlFlowNode):
                        first_node = node.test
                    else:
                        first_node = node
                cfg_statements.append(node)
        if prev_node_to_avoid:
            self.prev_nodes_to_avoid.pop()
        self.last_was_loop_stack.pop()
        logger.debug("Woah so first_node is %s", first_node)
        try:
            logger.debug("Woah so first_node.incoming is %s", first_node.incoming)
        except Exception:
            pass
        # logger.debug("A1A Beachfront Ave BEFORE cfg_statements[-1] are %s", cfg_statements[-1])
        # logger.debug("Hmm so type(cfg_statements) is %s", type(cfg_statements))
        for i,s in enumerate(cfg_statements):
            logger.debug("BEFORE SO MARG statement #%s is %s", i, s)

        self.connect_nodes(cfg_statements)
        for i,s in enumerate(cfg_statements):
            logger.debug("AFTER SO MARG statement #%s is %s", i, s)
        # logger.debug("A1A Beachfront Ave AFTER cfg_statements[-1] are %s", cfg_statements[-1])

        if cfg_statements:
            if first_node:
                first_statement = first_node
            else:
                first_statement = self.get_first_statement(cfg_statements[0])

            last_statements = self.get_last_statements(cfg_statements)
            logger.debug("Legal Pad] last_statements are %s", last_statements)
            return ConnectStatements(first_statement=first_statement, last_statements=last_statements, break_statements=break_nodes)
        else: # When body of module only contains ignored nodes
            return IgnoredNode()

    def visit_Module(self, node):
        return self.stmt_star_handler(node.body)

    def add_if_label(self, CFG_node):
        """Prepend 'if ' and append ':' to the label of a Node."""
        CFG_node.label = 'if ' + CFG_node.label + ':'

    def add_elif_label(self, CFG_node):
        """Add the el to an already add_if_label'ed Node."""
        CFG_node.label = 'el' + CFG_node.label

    def handle_or_else(self, orelse, test):
        """Handle the orelse part of an if or try node.

        Returns:
            The last nodes of the orelse branch.
        """
        logger.debug("orelse is %s", orelse)
        if isinstance(orelse[0], ast.If):
            control_flow_node = self.visit(orelse[0])
            self.add_elif_label(control_flow_node.test)
            test.connect(control_flow_node.test)
            return control_flow_node.last_nodes
        else:
            logger.debug("Ahh shit, so self.nodes[-1] is %s", self.nodes[-1])
            else_connect_statements = self.stmt_star_handler(orelse, prev_node_to_avoid=self.nodes[-1])
            logger.debug("hmm, connecting %s to %s", test, else_connect_statements.first_statement)
            test.connect(else_connect_statements.first_statement)
            return else_connect_statements.last_statements

    def remove_breaks(self, last_statements):
        """Remove all break statements in last_statements."""
        return [n for n in last_statements if not isinstance(n, BreakNode)]

    def visit_If(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node.test)

        test = self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

        self.add_if_label(test)

        body_connect_stmts = self.stmt_star_handler(node.body)
        if isinstance(body_connect_stmts, IgnoredNode):
            body_connect_stmts = ConnectStatements(first_statement=test, last_statements=[], break_statements=[])
        test.connect(body_connect_stmts.first_statement)

        if node.orelse:
            orelse_last_nodes = self.handle_or_else(node.orelse, test)
            body_connect_stmts.last_statements.extend(orelse_last_nodes)
        else:
            logger.debug("SO CONFUSED LETS SEE, So we are adding test %s to ", test)
            body_connect_stmts.last_statements.append(test) # if there is no orelse, test needs an edge to the next_node

        last_statements = self.remove_breaks(body_connect_stmts.last_statements)

        logger.debug("SO CONFUSED so last_statements is %s", last_statements)
        return ControlFlowNode(test, last_statements, break_statements=body_connect_stmts.break_statements)

    def visit_NameConstant(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node)
        logger.debug("[oslo] label_visitor.result is %s", label_visitor.result)
        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Raise(self, node):
        label = LabelVisitor()
        label.visit(node)

        return self.append_node(RaiseNode(label.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def handle_stmt_star_ignore_node(self, body, fallback_cfg_node):
        try:
            logger.debug("[Tuesday] so fallback_cfg_node %s is being connected to %s", fallback_cfg_node, body.first_statement)
            fallback_cfg_node.connect(body.first_statement)
        except AttributeError:
            body = ConnectStatements([fallback_cfg_node], [fallback_cfg_node], list())
        return body

    def visit_Try(self, node):
        try_node = self.append_node(Node('Try', node, line_number=node.lineno, path=self.filenames[-1]))
        body = self.stmt_star_handler(node.body)
        body = self.handle_stmt_star_ignore_node(body, try_node)

        last_statements = list()
        for handler in node.handlers:
            try:
                name = handler.type.id
            except AttributeError:
                name = ''
            handler_node = self.append_node(Node('except ' + name + ':', handler, line_number=handler.lineno, path=self.filenames[-1]))
            for body_node in body.last_statements:
                logger.debug("[Tuesday]connecting %s with %s", body_node, handler_node)
                body_node.connect(handler_node)
            handler_body = self.stmt_star_handler(handler.body)
            logger.debug("[sad panda] handler_node is %s", handler_node)
            logger.debug("[sad panda] handler_body.first_statement is %s", handler_body.first_statement)
            handler_body = self.handle_stmt_star_ignore_node(handler_body, handler_node)
            last_statements.extend(handler_body.last_statements)

        logger.debug("[Tuesday] BEFORE try_node is %s", try_node)
        if node.orelse:
            logger.debug("body.last_statements[-1] is %s", body.last_statements[-1])
            orelse_last_nodes = self.handle_or_else(node.orelse, body.last_statements[-1])
            body.last_statements.extend(orelse_last_nodes)
        logger.debug("[Tuesday] AFTER try_node is %s", try_node)

        if node.finalbody:
            finalbody = self.stmt_star_handler(node.finalbody)
            for last in last_statements:
                last.connect(finalbody.first_statement)

            for last in body.last_statements:
                last.connect(finalbody.first_statement)

            body.last_statements.extend(finalbody.last_statements)

        last_statements.extend(self.remove_breaks(body.last_statements))

        return ControlFlowNode(try_node, last_statements, break_statements=body.break_statements)

    def get_names(self, node, result):
        """Recursively finds all names."""
        if isinstance(node, ast.Name):
            return node.id + result
        elif isinstance(node, ast.Subscript):
            return result
        else:
            return self.get_names(node.value, result + '.' + node.attr)

    def extract_left_hand_side(self, target):
        """Extract the left hand side variable from a target.

        Removes list indexes, stars and other left hand side elements.
        """
        left_hand_side = self.get_names(target, '')

        left_hand_side.replace('*', '')
        if '[' in left_hand_side:
            index = left_hand_side.index('[')
            left_hand_side = target[0:index]

        return left_hand_side

    def assign_tuple_target(self, node, right_hand_side_variables):
        new_assignment_nodes = list()
        for i, target in enumerate(node.targets[0].elts):
            value = node.value.elts[i]

            label = LabelVisitor()
            label.visit(target)

            if isinstance(value, ast.Call):
                new_ast_node = ast.Assign(target, value)
                new_ast_node.lineno = node.lineno

                new_assignment_nodes.append(self.assignment_call_node(label.result, new_ast_node))

            else:
                label.result += ' = '
                label.visit(value)

                new_assignment_nodes.append(self.append_node(AssignmentNode(label.result, self.extract_left_hand_side(target), ast.Assign(target, value), right_hand_side_variables, None, line_number=node.lineno, path=self.filenames[-1])))


        self.connect_nodes(new_assignment_nodes)
        return ControlFlowNode(new_assignment_nodes[0], [new_assignment_nodes[-1]], []) # return the last added node

    def assign_multi_target(self, node, right_hand_side_variables):
        new_assignment_nodes = list()

        for target in node.targets:
            label = LabelVisitor()
            label.visit(target)
            left_hand_side = label.result
            label.result += ' = '
            label.visit(node.value)
            new_assignment_nodes.append(self.append_node(AssignmentNode(label.result, left_hand_side, ast.Assign(target, node.value), right_hand_side_variables, None, line_number=node.lineno, path=self.filenames[-1])))

        self.connect_nodes(new_assignment_nodes)
        return ControlFlowNode(new_assignment_nodes[0], [new_assignment_nodes[-1]], []) # return the last added node

    def visit_Assign(self, node):
        rhs_visitor = RHSVisitor()
        rhs_visitor.visit(node.value)
        if isinstance(node.targets[0], ast.Tuple): #  x,y = [1,2]
            if isinstance(node.value, ast.Tuple):
                return self.assign_tuple_target(node, rhs_visitor.result)
            elif isinstance(node.value, ast.Call):
                call = None
                for element in node.targets[0].elts:
                    label = LabelVisitor()
                    label.visit(element)
                    call = self.assignment_call_node(label.result, node)
                return call
            else:
                label = LabelVisitor()
                label.visit(node)
                print('Assignment not properly handled.',
                      'Could result in not finding a vulnerability.',
                      'Assignment:', label.result)
                return self.append_node(AssignmentNode(label.result, label.result, node, rhs_visitor.result, None, line_number=node.lineno, path=self.filenames[-1]))

        elif len(node.targets) > 1:                #  x = y = 3
            return self.assign_multi_target(node, rhs_visitor.result)
        else:
            if isinstance(node.value, ast.Call):   #  x = call()
                label = LabelVisitor()
                label.visit(node.targets[0])
                return self.assignment_call_node(label.result, node)
            else:                                  #  x = 4
                label = LabelVisitor()
                label.visit(node)
                return self.append_node(AssignmentNode(label.result, self.extract_left_hand_side(node.targets[0]), node, rhs_visitor.result, None, line_number=node.lineno, path=self.filenames[-1]))

    def assignment_call_node(self, left_hand_label, ast_node):
        """Handle assignments that contain a function call on its right side."""
        self.undecided = True # Used for handling functions in assignments

        call = self.visit(ast_node.value)
        logger.debug("[NYSEC] call is %s", call)
        logger.debug("[NYSEC] type(call) is %s", type(call))
        call_label = ''
        call_assignment = None
        if isinstance(call, AssignmentNode): #  assignment after returned nonbuiltin e.g. RestoreNode ¤call_1 = ret_outer
            # raise
            call_label = call.left_hand_side
            call_assignment = AssignmentNode(left_hand_label + ' = ' + call_label, left_hand_label, ast_node, [call.left_hand_side], None, line_number=ast_node.lineno, path=self.filenames[-1])
            call.connect(call_assignment)
        else: #  assignment to builtin
            # Consider using call.left_hand_side instead of call.label
            # logger.debug("call.left_hand_side is %s", call.left_hand_side)
            # raise
            # call_label = call.left_hand_side

            call_label = call.label
            rhs_visitor = RHSVisitor()
            rhs_visitor.visit(ast_node.value)

            # Necessary to know `image_name = image_name.replace('..', '')` is a reassignment.
            vars_visitor = VarsVisitor()
            vars_visitor.visit(ast_node.value)

            call_assignment = AssignmentNode(left_hand_label + ' = ' + call_label, left_hand_label, ast_node, rhs_visitor.result, vars_visitor.result, line_number=ast_node.lineno, path=self.filenames[-1])

        if call in self.blackbox_calls:
            self.blackbox_assignments.add(call_assignment)
            call_assignment.blackbox = True

        self.nodes.append(call_assignment)

        self.undecided = False

        return call_assignment

    def visit_AugAssign(self, node):
        label = LabelVisitor()
        label.visit(node)

        rhs_visitor = RHSVisitor()
        rhs_visitor.visit(node.value)

        return self.append_node(AssignmentNode(label.result, self.extract_left_hand_side(node.target), node, rhs_visitor.result, None, line_number=node.lineno, path=self.filenames[-1]))

    def loop_node_skeleton(self, test, node):
        """Common handling of looped structures, while and for."""
        body_connect_stmts = self.stmt_star_handler(node.body, prev_node_to_avoid=self.nodes[-1])

        test.connect(body_connect_stmts.first_statement)
        test.connect_predecessors(body_connect_stmts.last_statements)

        # last_nodes is used for making connections to the next node in the parent node
        # this is handled in stmt_star_handler
        last_nodes = list()
        last_nodes.extend(body_connect_stmts.break_statements)

        if node.orelse:
            orelse_connect_stmts = self.stmt_star_handler(node.orelse, prev_node_to_avoid=self.nodes[-1])

            test.connect(orelse_connect_stmts.first_statement)
            last_nodes.extend(orelse_connect_stmts.last_statements)
        else:
            last_nodes.append(test)  # if there is no orelse, test needs an edge to the next_node

        logger.debug("[broke] last_nodes are %s", last_nodes)
        return ControlFlowNode(test, last_nodes, list())

    def add_while_label(self, node):
        """Prepend 'while' and append ':' to the label of a node."""
        node.label = 'while ' + node.label + ':'

    def visit_While(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node.test)

        test = self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

        self.add_while_label(test)

        return self.loop_node_skeleton(test, node)

    def visit_For(self, node):
        self.undecided = True  # Used for handling functions in for loops

        iterator_label = LabelVisitor()
        iterator = iterator_label.visit(node.iter)
        self.undecided = False

        target_label = LabelVisitor()
        target = target_label.visit(node.target)

        for_node = self.append_node(Node("for " + target_label.result + " in " + iterator_label.result + ':', node, line_number=node.lineno, path=self.filenames[-1]))

        if isinstance(node.iter, ast.Call) and get_call_names_as_string(node.iter.func) in self.function_names:
            last_node = self.visit(node.iter)
            last_node.connect(for_node)

        return self.loop_node_skeleton(for_node, node)

    def visit_Expr(self, node):
        return self.visit(node.value)

    def add_blackbox_or_builtin_call(self, node, blackbox=False):
        """Processes a blackbox or builtin function when it is called.

        Increments self.function_call_index each time it is called, we can refer to it as N in the comments.
        Create e.g. ¤call_1 = ret_func_foo RestoreNode.
        Create e.g. temp_N_def_arg1 = call_arg1_label_visitor.result for each argument. Visit the arguments if they're calls. (save_def_args_in_temp)
        I do not think I care about this one actually -- Create e.g. def_arg1 = temp_N_def_arg1 for each argument. (create_local_scope_from_def_args)
        Add RestoreNode to the end of the Nodes.

        Args:
            node()
            blackbox(bool): Whether or not it is a builtin or blackbox call.
        Returns:
            FILL ME IN
        """

        logger.debug("[qq] ENTER self.blackbox_calls is %s", self.blackbox_calls)
        # Increment function_call_index
        self.function_call_index += 1
        saved_function_call_index = self.function_call_index
        self.undecided = False

        label = LabelVisitor()
        label.visit(node)

        logger.debug("[PR] the label.result is %s", label.result)
        index = label.result.find('(')
        if index == -1:
            logger.warning("No ( in a call")
            raise
        else:
            logger.debug("[3rd rail] the call is %s", label.result[:index])
            logger.debug("[3rd rail] the args are %s", label.result[index:])
            logger.debug("[3rd rail] len(node.args) is %s", len(node.args))
            logger.debug("[3rd rail] len(node.keywords) is %s", len(node.keywords))
            try:
                logger.debug("[3rd rail] len(node.starargs) is %s", len(node.starargs))
            except AttributeError:
                pass
            try:
                logger.debug("[3rd rail] len(node.keywords) is %s", len(node.keywords))
            except AttributeError:
                pass

        # Create e.g. ¤call_1 = ret_func_foo
        LHS = CALL_IDENTIFIER + 'call_' + str(saved_function_call_index)
        RHS = 'ret_' + label.result[:index] + '('
        logger.debug("[Dominique bistro] RHS is %s", RHS)
        call_node = BBnode("",
                           LHS,
                           [],
                           line_number=node.lineno,
                           path=self.filenames[-1])

        # visited_args = []
        visual_args = []
        rhs_vars = []
        for arg in itertools.chain(node.args, node.keywords):
            if isinstance(arg, ast.Call):
                # logger.debug("[Dominique bistro] function_return_stack[-1] is %s", self.function_return_stack[-1])
                return_value_of_nested_call = self.visit(arg)
                # logger.debug("[Dominique bistro] function_return_stack[-1] is %s", self.function_return_stack[-1])
                logger.debug("[OSLO WAS SO GOOD] return_value_of_nested_call is %s", return_value_of_nested_call)
                logger.debug("[OSLO WAS SO GOOD] self.nodes is %s", self.nodes)
                # for n in self.nodes:
                #     if n == return_value_of_nested_call:
                #         raise
                logger.debug("BNBN So self.nodes[-1] is %s", self.nodes[-1])
                logger.debug("BNBN About to append %s", return_value_of_nested_call)
                return_value_of_nested_call.connect(call_node)
                # visited_args.append(return_value_of_nested_call)

                logger.debug("[3rd rail] should we add %s to visual_args?", return_value_of_nested_call.left_hand_side)
                visual_args.append(return_value_of_nested_call.left_hand_side)
                rhs_vars.append(return_value_of_nested_call.left_hand_side)
            else:
                label = LabelVisitor()
                label.visit(arg)
                logger.debug("arg is %s, and label.result is %s", arg, label.result)
                visual_args.append(label.result)
                # visited_args.append(arg)

                from .vars_visitor import VarsVisitor
                vv = VarsVisitor()
                vv.visit(arg)
                logger.debug("[BLUESTONE sucks] type(arg) is %s", type(arg))
                logger.debug("[BLUESTONE sucks] vv.result is %s", vv.result)
                rhs_vars.extend(vv.result)
            logger.debug("[Voyager] arg is %s", arg)
        #####

        logger.debug("[3rd rail] visual_args is %s", visual_args)
        # logger.debug("[3rd rail] visited_args is %s", visited_args)

        logger.debug("[VINEAPPLE] label.result is %s", label.result)
        if len(visual_args) > 0:
            for arg in visual_args:
                RHS = RHS + arg + ", "
            logger.debug("[3rd rail] RHS[:len(RHS)-2] is %s", RHS[:len(RHS)-2])
            # Replace the last ", " with a )
            RHS = RHS[:len(RHS)-2] + ')'
        else:
            RHS = RHS + ')'
        logger.debug("[Dominique bistro] RHS is now %s", RHS)
        call_node.label = LHS + " = " + RHS
        # get_rhs = []
        # for arg in visited_args:
        #     try:
        #         logger.debug("[BLUESTONE sucks] type(arg.right_hand_side_variables) is %s", arg.right_hand_side_variables)
        #         get_rhs.extend(arg.right_hand_side_variables)
        #     except AttributeError:
        #         from .vars_visitor import VarsVisitor
        #         vv = VarsVisitor()
        #         vv.visit(arg)
        #         logger.debug("[BLUESTONE sucks] type(arg) is %s", type(arg))
        #         logger.debug("[BLUESTONE sucks] vv.result is %s", vv.result)
        #         get_rhs.extend(vv.result)
        # logger.debug("[qq] get_rhs is %s", get_rhs)
        # Should strings be excluded from visual_args? It isn't like they'll ever be on an LHS
        logger.debug("[qq] visual_args is %s", visual_args)
        logger.debug("[qq] rhs_vars is %s", rhs_vars)

        # This is where we'll ask the user, then save the mapping or just use the pre-made mapping.
        # Or perhaps we'll do that in vulnerabilities.py

        call_node.right_hand_side_variables = rhs_vars
        # DOCUMENT THE NEEED FOR BB_node.args, was it just for get_sink_args?
        # DOCUMENT THE NEEED FOR BB_node.args, was it just for get_sink_args?
        # DOCUMENT THE NEEED FOR BB_node.args, was it just for get_sink_args?
        # DOCUMENT THE NEEED FOR BB_node.args, was it just for get_sink_args?
        call_node.args = rhs_vars
        # What is assigned to ret_func_foo in the builtin/blackbox case?
        # What is assigned to ret_func_foo in the builtin/blackbox case?
        # What is assigned to ret_func_foo in the builtin/blackbox case?

        if blackbox:
            logger.debug("[qq] call_node being added to blackbox_calls is %s", call_node)
            # This makes so much sense!
            self.blackbox_assignments.add(call_node)

        # IMPORTANT
        logger.debug("[Integral] connecting %s", self.nodes[-1])
        logger.debug("[Integral] to call_node %s", call_node)
        logger.debug("ON&ON self.nodes[-1] IS %s", self.nodes[-1])
        logger.debug("ON&ON call_node IS %s", call_node)
        self.connect_if_allowed(self.nodes[-1], call_node)
        self.nodes.append(call_node)
        # IMPORTANT

        logger.debug("[Dominique bistro] call_node is %s", call_node)
        # WHY DO WE DO THIS?
        # WHEN DO WE ACTUALLY PUSH?
        # self.function_return_stack.pop()
        logger.debug("[qq] EXIT self.blackbox_calls is %s", self.blackbox_calls)

        return call_node

    def visit_Name(self, node):
        label = LabelVisitor()
        label.visit(node)

        return self.append_node(Node(label.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_With(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node.items[0])

        with_node = self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))
        connect_statements = self.stmt_star_handler(node.body)
        with_node.connect(connect_statements.first_statement)
        return ControlFlowNode(with_node, connect_statements.last_statements, connect_statements.break_statements)

    def visit_Str(self, node):
        return IgnoredNode()

    def visit_Break(self, node):
        return self.append_node(BreakNode(node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Pass(self, node):
        return self.append_node(Node('pass', node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Continue(self, node):
        return self.append_node(Node('continue', node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Delete(self, node):
        labelVisitor = LabelVisitor()
        for expr in node.targets:
            labelVisitor.visit(expr)
        return self.append_node(Node('del ' + labelVisitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Assert(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node.test)

        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Attribute(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node)

        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Global(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node)

        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Subscript(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node)

        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))

    def visit_Tuple(self, node):
        label_visitor = LabelVisitor()
        label_visitor.visit(node)

        return self.append_node(Node(label_visitor.result, node, line_number=node.lineno, path=self.filenames[-1]))
